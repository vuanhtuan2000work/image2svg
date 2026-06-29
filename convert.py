import argparse
import base64
import html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import vtracer
import yaml
from PIL import Image, ImageChops, ImageFilter

from background_removal import get_last_background_engine, remove_background

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pillow_heif = None

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "assets" / "raw"
OUT_DIR = ROOT / "assets" / "out"
RECIPES = ROOT / "recipes.yaml"

VTRACER_KEYS = {
    "colormode",
    "hierarchical",
    "mode",
    "filter_speckle",
    "color_precision",
    "layer_difference",
    "corner_threshold",
    "length_threshold",
    "max_iterations",
    "splice_threshold",
    "path_precision",
}

# Preset làm mịn rìa: CHỈ upscale ảnh (nội suy Lanczos) TRƯỚC khi trace. Lanczos tự
# tạo cạnh chuyển màu mượt (anti-alias) ở RÌA nên vtracer fit spline cong thay vì bám
# pixel răng cưa — mà KHÔNG đụng tới màu/hình bên trong.
# KHÔNG dùng GaussianBlur: blur làm mịn cả vùng màu -> méo hình, mất highlight.
SMOOTHING_PRESETS = {
    "none": {"upscale": 1, "blur": 0.0},
    "low": {"upscale": 2, "blur": 0.0},
    "medium": {"upscale": 3, "blur": 0.0},
    "high": {"upscale": 4, "blur": 0.0},
}
DEFAULT_SMOOTHING = "medium"
DEFAULT_SHARPNESS = 80
OUTPUT_FORMATS = ("jpg", "jpeg", "png", "webp", "avif", "gif", "svg", "bmp", "tiff", "heic")
SVG_MODES = ("embedded", "vector")
RASTER_OUTPUT_FORMATS = tuple(fmt for fmt in OUTPUT_FORMATS if fmt != "svg")
RASTER_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "heic": "image/heic",
}
PIL_SAVE_FORMATS = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
    "gif": "GIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "heic": "HEIF",
}
NO_ALPHA_OUTPUTS = {"jpg", "jpeg", "bmp"}


@dataclass(frozen=True)
class TracePlan:
    image_bytes: bytes
    suffix: str
    params: dict
    orig_size: tuple[int, int] | None
    upscale: int


def load_recipes() -> dict:
    with open(RECIPES) as f:
        data = yaml.safe_load(f) or {}
    return data


def recipe_for(part: str, recipes: dict) -> dict:
    base = dict(recipes.get("default", {}))
    base.update(recipes.get("parts", {}).get(part, {}))
    return {k: v for k, v in base.items() if k in VTRACER_KEYS}


def detect_optimizer() -> str:
    if shutil.which("npx"):
        return "svgo"
    try:
        import scour  # noqa: F401

        return "scour"
    except ImportError:
        return "none"


def optimize(svg_path: Path, optimizer: str) -> None:
    if optimizer == "svgo":
        try:
            subprocess.run(
                ["npx", "--yes", "svgo", str(svg_path), "-o", str(svg_path), "--multipass"],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # SVGO lỗi nhất thời (npx resolve, timeout...) -> giữ SVG chưa optimize.
            print(f"[warn] SVGO bỏ qua ({type(exc).__name__}): {svg_path.name}", file=sys.stderr)
    elif optimizer == "scour":
        from scour import scour as scour_mod

        opts = scour_mod.parse_args(
            [
                "--enable-id-stripping",
                "--shorten-ids",
                "--remove-metadata",
                "--enable-comment-stripping",
                "--set-precision=3",
            ]
        )
        src = svg_path.read_text()
        svg_path.write_text(scour_mod.scourString(src, opts))


def _detect_bg_color(img: "Image.Image") -> tuple[int, int, int]:
    """Lấy màu nền từ trung vị các pixel viền (4 cạnh)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    samples: list[tuple[int, int, int]] = []
    step_x = max(1, w // 40)
    step_y = max(1, h // 40)
    for x in range(0, w, step_x):
        samples.append(px[x, 0])
        samples.append(px[x, h - 1])
    for y in range(0, h, step_y):
        samples.append(px[0, y])
        samples.append(px[w - 1, y])
    channels = list(zip(*samples))
    return tuple(int(sorted(c)[len(c) // 2]) for c in channels)  # type: ignore[return-value]


def trim_to_content(img: "Image.Image") -> "Image.Image":
    """Cắt sát nội dung (bỏ padding). Ưu tiên alpha, fallback theo màu nền."""
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()

    if bbox is None or bbox == (0, 0, img.width, img.height):
        # Nền chưa trong suốt -> dò bbox theo độ lệch so với màu nền.
        bg = _detect_bg_color(img)
        diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, bg))
        bbox = diff.convert("L").point(lambda p: 255 if p > 16 else 0).getbbox()

    if bbox:
        img = img.crop(bbox)
    return img


def preprocess_image(
    image_bytes: bytes,
    *,
    upscale: int = 1,
    blur: float = 0.0,
    sharpen: float = 0.0,
    remove_bg: bool = False,
    bg_tolerance: int = 32,
    trim: bool = False,
) -> tuple[bytes, tuple[int, int]]:
    """Tiền xử lý ảnh trước khi trace. Trả về (png_bytes, (w, h) nội dung).

    Thứ tự: xóa nền -> cắt padding -> upscale (Lanczos) -> sharpen -> blur.
    orig_size lấy SAU khi cắt padding nên viewBox SVG ôm sát nội dung.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")

    if remove_bg:
        img = remove_background(img, tolerance=bg_tolerance)

    if trim:
        img = trim_to_content(img)

    orig_size = img.size

    if upscale > 1:
        img = img.resize((img.width * upscale, img.height * upscale), Image.LANCZOS)

    if sharpen > 0:
        # percent 0..~250; radius theo upscale để nét đều ở mọi mức phóng.
        radius = max(1.0, upscale * 0.6)
        img = img.filter(
            ImageFilter.UnsharpMask(radius=radius, percent=int(sharpen), threshold=2)
        )

    if blur > 0:
        # Bán kính tuyệt đối, nhỏ — chỉ xóa răng cưa còn sót sau upscale, không
        # đủ mạnh để gộp các vùng màu (iris/pupil/highlight) lại với nhau.
        img = img.filter(ImageFilter.GaussianBlur(radius=blur))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), orig_size


def _flatten_alpha(img: "Image.Image", background: tuple[int, int, int] = (255, 255, 255)) -> "Image.Image":
    img = img.convert("RGBA")
    canvas = Image.new("RGBA", img.size, (*background, 255))
    return Image.alpha_composite(canvas, img).convert("RGB")


def _save_raster_image(img: "Image.Image", output_type: str) -> bytes:
    output_type = output_type.lower()
    if output_type not in RASTER_OUTPUT_FORMATS:
        raise ValueError(f"Định dạng output không hỗ trợ: {output_type}")

    save_format = PIL_SAVE_FORMATS[output_type]
    save_img = _flatten_alpha(img) if output_type in NO_ALPHA_OUTPUTS else img.convert("RGBA")
    save_kwargs: dict = {}

    if output_type in {"jpg", "jpeg"}:
        save_kwargs.update({"quality": 95, "optimize": True, "progressive": True})
    elif output_type == "webp":
        save_kwargs.update({"quality": 95, "method": 6})
    elif output_type == "avif":
        save_kwargs.update({"quality": 95})
    elif output_type == "heic":
        save_kwargs.update({"quality": 95})

    if output_type == "gif":
        save_img = save_img.convert("RGBA")

    buf = BytesIO()
    try:
        save_img.save(buf, format=save_format, **save_kwargs)
    except Exception as exc:
        raise RuntimeError(f"Không thể xuất {output_type.upper()}: {exc}") from exc
    return buf.getvalue()


def _png_bytes_for_svg_embed(img: "Image.Image") -> bytes:
    buf = BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _svg_embed_image(png_bytes: bytes, width: int, height: int) -> str:
    href = base64.b64encode(png_bytes).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<image href="data:image/png;base64,{html.escape(href, quote=True)}" '
        f'width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet"/>'
        "</svg>"
    )


def convert_embedded_svg_bytes(
    image_bytes: bytes,
    *,
    smoothing: str = DEFAULT_SMOOTHING,
    sharpness: int = DEFAULT_SHARPNESS,
    remove_bg: bool = False,
    trim: bool = False,
) -> tuple[str, dict, str, float]:
    """Wrap the image in SVG without vector tracing, preserving raster colors."""
    t0 = time.time()
    preset = SMOOTHING_PRESETS.get(smoothing, SMOOTHING_PRESETS[DEFAULT_SMOOTHING])
    png_bytes, _orig_size = preprocess_image(
        image_bytes,
        upscale=int(preset["upscale"]),
        blur=float(preset["blur"]),
        sharpen=max(0, min(250, int(sharpness))),
        remove_bg=remove_bg,
        trim=trim,
    )
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")

    png_bytes = _png_bytes_for_svg_embed(img)
    svg = _svg_embed_image(png_bytes, img.width, img.height)
    report = {
        "svg_mode": "embedded",
        "source": "embedded-raster",
        "smoothing": smoothing,
        "upscale": int(preset["upscale"]),
        "sharpness": sharpness,
        "width": img.width,
        "height": img.height,
        "remove_bg": remove_bg,
        "trim": trim,
    }
    if remove_bg:
        report["remove_bg_engine"] = get_last_background_engine()
    return svg, report, "none", time.time() - t0


def convert_raster_image_bytes(
    image_bytes: bytes,
    *,
    output_type: str,
    smoothing: str = "none",
    sharpness: int = DEFAULT_SHARPNESS,
    remove_bg: bool = False,
    trim: bool = False,
) -> tuple[bytes, dict, str, str, float]:
    """Transcode image bytes to a raster format with optional image preprocessing."""
    output_type = output_type.lower()
    if output_type not in RASTER_OUTPUT_FORMATS:
        raise ValueError(f"Định dạng output không hỗ trợ: {output_type}")

    t0 = time.time()
    preset = SMOOTHING_PRESETS.get(smoothing, SMOOTHING_PRESETS["none"])
    png_bytes, _orig_size = preprocess_image(
        image_bytes,
        upscale=int(preset["upscale"]),
        blur=float(preset["blur"]),
        sharpen=max(0, min(250, int(sharpness))),
        remove_bg=remove_bg,
        trim=trim,
    )
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    payload = _save_raster_image(img, output_type)
    report = {
        "format": output_type,
        "source": "raster-image",
        "smoothing": smoothing,
        "upscale": int(preset["upscale"]),
        "sharpness": sharpness,
        "width": img.width,
        "height": img.height,
        "remove_bg": remove_bg,
        "trim": trim,
    }
    if remove_bg:
        report["remove_bg_engine"] = get_last_background_engine()
    if output_type in NO_ALPHA_OUTPUTS and img.mode == "RGBA":
        report["flattened_background"] = "white"
    return payload, report, RASTER_MIME_TYPES[output_type], output_type, time.time() - t0


def _scale_params_for_upscale(params: dict, upscale: int) -> dict:
    """Scale ngưỡng theo upscale (tuyến tính) để giữ chi tiết nhỏ sau khi phóng to.

    Cố ý KHÔNG scale theo upscale^2: scale bình phương sẽ xoá luôn highlight/đốm nhỏ
    (đã to lên sau upscale) -> mất chuẩn hình. Tuyến tính giữ noise-filter vừa phải.
    """
    if upscale <= 1:
        return params
    out = dict(params)
    if "filter_speckle" in out:
        out["filter_speckle"] = max(1, round(out["filter_speckle"] * upscale))
    if "length_threshold" in out:
        out["length_threshold"] = out["length_threshold"] * upscale
    return out


def _params_for_part(part: str, recipes: dict) -> dict:
    if part == "default":
        return {k: v for k, v in (recipes.get("default") or {}).items() if k in VTRACER_KEYS}
    return recipe_for(part, recipes)


def _apply_color_precision(params: dict, color_precision: int | None) -> dict:
    if color_precision is None:
        return params
    out = dict(params)
    # vtracer color_precision = số bit/kênh, hợp lệ 1..8 (cao = nhiều màu/chuẩn hơn).
    out["color_precision"] = max(1, min(8, int(color_precision)))
    return out


def _trace_preset(smoothing: str) -> tuple[int, float]:
    preset = SMOOTHING_PRESETS.get(smoothing, SMOOTHING_PRESETS["none"])
    return preset["upscale"], preset["blur"]


def _prepare_trace_plan(
    image_bytes: bytes,
    *,
    suffix: str,
    params: dict,
    smoothing: str,
    sharpness: int,
    remove_bg: bool,
    trim: bool,
) -> TracePlan:
    upscale, blur = _trace_preset(smoothing)
    needs_pre = upscale > 1 or blur > 0 or sharpness > 0 or remove_bg or trim

    if not needs_pre:
        return TracePlan(
            image_bytes=image_bytes,
            suffix=suffix,
            params=params,
            orig_size=None,
            upscale=upscale,
        )

    trace_bytes, orig_size = preprocess_image(
        image_bytes,
        upscale=upscale,
        blur=blur,
        sharpen=sharpness,
        remove_bg=remove_bg,
        trim=trim,
    )
    return TracePlan(
        image_bytes=trace_bytes,
        suffix=".png",
        params=_scale_params_for_upscale(params, upscale),
        orig_size=orig_size,
        upscale=upscale,
    )


def _write_trace_plan(plan: TracePlan, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_src = Path(tmp) / f"input{plan.suffix}"
        tmp_src.write_bytes(plan.image_bytes)
        vtracer.convert_image_to_svg_py(str(tmp_src), str(dst), **plan.params)


def _trace_plan_to_svg(plan: TracePlan, optimizer: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "output.svg"
        _write_trace_plan(plan, dst)
        if optimizer != "none":
            optimize(dst, optimizer)
        return dst.read_text(encoding="utf-8")


def convert_one(
    src: Path,
    dst: Path,
    params: dict,
    optimizer: str,
    smoothing: str = "none",
    *,
    sharpness: int = DEFAULT_SHARPNESS,
    remove_bg: bool = False,
    trim: bool = False,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    plan = _prepare_trace_plan(
        src.read_bytes(),
        suffix=src.suffix.lower() or ".png",
        params=params,
        smoothing=smoothing,
        sharpness=sharpness,
        remove_bg=remove_bg,
        trim=trim,
    )

    if plan.orig_size is not None:
        _write_trace_plan(plan, dst)
        dst.write_text(
            _normalize_svg_size(dst.read_text(encoding="utf-8"), plan.orig_size[0], plan.orig_size[1]),
            encoding="utf-8",
        )
    else:
        vtracer.convert_image_to_svg_py(str(src), str(dst), **params)

    if optimizer != "none":
        optimize(dst, optimizer)


def list_part_types(recipes: dict | None = None) -> list[str]:
    data = recipes if recipes is not None else load_recipes()
    # Giữ thứ tự khai báo trong recipes.yaml (nhóm theo vùng cơ thể) thay vì sort.
    return list((data.get("parts") or {}).keys())


def _normalize_svg_size(svg: str, orig_w: int, orig_h: int) -> str:
    """Sau khi upscale, vtracer ghi width/height theo kích thước phóng to.

    Ép width/height về kích thước gốc + thêm viewBox để SVG hiển thị đúng tỉ lệ
    (    path bên trong giữ độ phân giải cao nên vẫn mượt khi zoom).
    """
    m = re.search(r'<svg[^>]*\bwidth="(\d+(?:\.\d+)?)"[^>]*\bheight="(\d+(?:\.\d+)?)"', svg)
    if not m:
        return svg
    up_w, up_h = float(m.group(1)), float(m.group(2))

    def repl(match: "re.Match") -> str:
        tag = match.group(0)
        if "viewBox" not in tag:
            tag = tag.replace("<svg", f'<svg viewBox="0 0 {up_w:g} {up_h:g}"', 1)
        tag = re.sub(r'\bwidth="[^"]*"', f'width="{orig_w}"', tag, count=1)
        tag = re.sub(r'\bheight="[^"]*"', f'height="{orig_h}"', tag, count=1)
        return tag

    return re.sub(r"<svg[^>]*>", repl, svg, count=1)


def convert_image_bytes(
    image_bytes: bytes,
    *,
    part: str = "default",
    suffix: str = ".png",
    optimizer: str | None = None,
    recipes: dict | None = None,
    smoothing: str = DEFAULT_SMOOTHING,
    color_precision: int | None = None,
    sharpness: int = DEFAULT_SHARPNESS,
    remove_bg: bool = False,
    trim: bool = False,
) -> tuple[str, dict, str, float]:
    """Trace PNG bytes to SVG text. Returns (svg, params, optimizer, elapsed_s)."""
    data = recipes if recipes is not None else load_recipes()
    params = _apply_color_precision(_params_for_part(part, data), color_precision)
    opt = optimizer if optimizer is not None else detect_optimizer()
    t0 = time.time()

    plan = _prepare_trace_plan(
        image_bytes,
        suffix=suffix,
        params=params,
        smoothing=smoothing,
        sharpness=sharpness,
        remove_bg=remove_bg,
        trim=trim,
    )
    svg = _trace_plan_to_svg(plan, opt)

    # Sau preprocess, ép width/height + viewBox về kích thước nội dung (đã trim).
    if plan.orig_size is not None:
        svg = _normalize_svg_size(svg, plan.orig_size[0], plan.orig_size[1])

    report = dict(params)
    report["smoothing"] = smoothing
    report["upscale"] = plan.upscale
    report["sharpness"] = sharpness
    report["remove_bg"] = remove_bg
    if remove_bg:
        report["remove_bg_engine"] = get_last_background_engine()
    report["trim"] = trim
    return svg, report, opt, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch PNG -> SVG (vtracer + optimize)")
    ap.add_argument("--part", help="Chỉ chạy 1 part_type (vd: eye). Bỏ trống = chạy tất cả.")
    ap.add_argument("--overwrite", action="store_true", help="Ghi đè SVG đã tồn tại.")
    ap.add_argument(
        "--smoothing",
        choices=list(SMOOTHING_PRESETS.keys()),
        default=DEFAULT_SMOOTHING,
        help="Mức làm mịn rìa (upscale+blur trước trace). Mặc định: %(default)s.",
    )
    ap.add_argument(
        "--color-precision",
        type=int,
        default=None,
        help="Độ chính xác màu 1-8 (cao = nhiều màu/chuẩn hơn). Mặc định theo recipe.",
    )
    ap.add_argument(
        "--sharpness",
        type=int,
        default=DEFAULT_SHARPNESS,
        help="Độ rõ nét 0-250 (unsharp mask trước trace). Mặc định: %(default)s.",
    )
    ap.add_argument("--remove-bg", action="store_true", help="Xóa nền (-> trong suốt).")
    ap.add_argument("--trim", action="store_true", help="Cắt padding, ôm sát nội dung.")
    args = ap.parse_args()

    recipes = load_recipes()
    optimizer = detect_optimizer()
    if optimizer == "none":
        print("[warn] Không tìm thấy SVGO hoặc scour -> bỏ qua bước optimize.")

    if args.part:
        parts = [args.part]
    elif RAW_DIR.exists():
        parts = [d.name for d in RAW_DIR.iterdir() if d.is_dir()]
    else:
        parts = []

    total, skipped, t0 = 0, 0, time.time()

    for part in parts:
        part_dir = RAW_DIR / part
        if not part_dir.is_dir():
            print(f"[warn] Không tìm thấy folder raw/{part}/", file=sys.stderr)
            continue

        params = recipe_for(part, recipes)
        if args.color_precision is not None:
            params["color_precision"] = max(1, min(8, args.color_precision))
        for src in sorted(part_dir.glob("*.png")):
            dst = OUT_DIR / part / (src.stem + ".svg")
            if dst.exists() and not args.overwrite:
                skipped += 1
                continue
            print(f"[{part}] {src.name} -> {dst.relative_to(ROOT)}")
            convert_one(
                src,
                dst,
                params,
                optimizer,
                smoothing=args.smoothing,
                sharpness=args.sharpness,
                remove_bg=args.remove_bg,
                trim=args.trim,
            )
            total += 1

    print(
        f"\nXong: {total} file ({skipped} bỏ qua) trong {time.time() - t0:.1f}s "
        f"| optimizer={optimizer} | smoothing={args.smoothing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
