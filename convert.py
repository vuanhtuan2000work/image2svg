import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path

import vtracer
import yaml
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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


def remove_background(img: "Image.Image", *, tolerance: int = 32) -> "Image.Image":
    """Xóa nền: flood-fill từ viền các pixel gần màu nền -> alpha = 0.

    Dùng flood-fill (chỉ vùng nền nối liền với viền) nên các vùng sáng/trắng NẰM
    TRONG object (lòng trắng mắt, highlight) được giữ lại.
    """
    img = img.convert("RGBA")
    w, h = img.size
    bg = _detect_bg_color(img)

    # Sentinel khác hẳn màu nền để không trùng nội dung.
    sentinel = (255, 0, 255) if bg != (255, 0, 255) else (0, 255, 0)
    work = img.convert("RGB")

    seeds: list[tuple[int, int]] = []
    step_x = max(1, w // 30)
    step_y = max(1, h // 30)
    for x in range(0, w, step_x):
        seeds.extend([(x, 0), (x, h - 1)])
    for y in range(0, h, step_y):
        seeds.extend([(0, y), (w - 1, y)])

    for seed in seeds:
        if work.getpixel(seed) == sentinel:
            continue
        ImageDraw.floodfill(work, seed, sentinel, thresh=tolerance)

    # bg_mask: pixel == sentinel -> nền
    diff = ImageChops.difference(work, Image.new("RGB", img.size, sentinel)).convert("L")
    bg_mask = diff.point(lambda p: 255 if p == 0 else 0)  # 255 ở vùng nền

    alpha = img.getchannel("A")
    alpha = ImageChops.subtract(alpha, bg_mask)  # set 0 ở vùng nền
    img.putalpha(alpha)

    # Bỏ các mảnh rời rạc còn sót (viền/vệt sáng của thẻ...) -> chỉ giữ object chính.
    img = _keep_main_components(img, min_ratio=0.10)
    return img


def _keep_main_components(img: "Image.Image", *, min_ratio: float = 0.10) -> "Image.Image":
    """Giữ các vùng đục (alpha>0) đủ lớn, xoá mảnh nhỏ rời rạc.

    Gán nhãn connected-component (4-hướng) trên mask alpha rồi giữ những component có
    diện tích >= min_ratio * (component lớn nhất). Loại bỏ thanh/vụn nổi quanh object.
    """
    img = img.convert("RGBA")
    w, h = img.size
    alpha = img.getchannel("A")
    fg = [1 if v > 8 else 0 for v in alpha.getdata()]

    labels = [0] * (w * h)
    sizes: list[int] = [0]  # index 0 = nền
    current = 0
    for start in range(w * h):
        if fg[start] == 0 or labels[start] != 0:
            continue
        current += 1
        count = 0
        stack = [start]
        labels[start] = current
        while stack:
            idx = stack.pop()
            count += 1
            x, y = idx % w, idx // w
            if x > 0 and fg[idx - 1] and labels[idx - 1] == 0:
                labels[idx - 1] = current
                stack.append(idx - 1)
            if x < w - 1 and fg[idx + 1] and labels[idx + 1] == 0:
                labels[idx + 1] = current
                stack.append(idx + 1)
            if y > 0 and fg[idx - w] and labels[idx - w] == 0:
                labels[idx - w] = current
                stack.append(idx - w)
            if y < h - 1 and fg[idx + w] and labels[idx + w] == 0:
                labels[idx + w] = current
                stack.append(idx + w)
        sizes.append(count)

    if current <= 1:
        return img

    threshold = max(sizes) * min_ratio
    keep = {i for i in range(1, current + 1) if sizes[i] >= threshold}

    old_alpha = list(alpha.getdata())
    new_alpha = bytes(
        old_alpha[i] if labels[i] in keep else 0 for i in range(w * h)
    )
    img.putalpha(Image.frombytes("L", (w, h), new_alpha))
    return img


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


def convert_one(
    src: Path,
    dst: Path,
    params: dict,
    optimizer: str,
    smoothing: str = "none",
    *,
    sharpness: int = 0,
    remove_bg: bool = False,
    trim: bool = False,
) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    preset = SMOOTHING_PRESETS.get(smoothing, SMOOTHING_PRESETS["none"])
    upscale, blur = preset["upscale"], preset["blur"]
    needs_pre = upscale > 1 or blur > 0 or sharpness > 0 or remove_bg or trim

    if needs_pre:
        png_bytes, orig_size = preprocess_image(
            src.read_bytes(),
            upscale=upscale,
            blur=blur,
            sharpen=sharpness,
            remove_bg=remove_bg,
            trim=trim,
        )
        scaled = _scale_params_for_upscale(params, upscale)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_src = Path(tmp) / "pre.png"
            tmp_src.write_bytes(png_bytes)
            vtracer.convert_image_to_svg_py(str(tmp_src), str(dst), **scaled)
        dst.write_text(
            _normalize_svg_size(dst.read_text(encoding="utf-8"), orig_size[0], orig_size[1]),
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
    sharpness: int = 0,
    remove_bg: bool = False,
    trim: bool = False,
) -> tuple[str, dict, str, float]:
    """Trace PNG bytes to SVG text. Returns (svg, params, optimizer, elapsed_s)."""
    data = recipes if recipes is not None else load_recipes()
    if part == "default":
        params = {k: v for k, v in (data.get("default") or {}).items() if k in VTRACER_KEYS}
    else:
        params = recipe_for(part, data)

    if color_precision is not None:
        # vtracer color_precision = số bit/kênh, hợp lệ 1..8 (cao = nhiều màu/chuẩn hơn).
        params["color_precision"] = max(1, min(8, int(color_precision)))

    opt = optimizer if optimizer is not None else detect_optimizer()
    preset = SMOOTHING_PRESETS.get(smoothing, SMOOTHING_PRESETS["none"])
    upscale, blur = preset["upscale"], preset["blur"]
    t0 = time.time()

    needs_pre = upscale > 1 or blur > 0 or sharpness > 0 or remove_bg or trim
    trace_bytes = image_bytes
    orig_size: tuple[int, int] | None = None
    trace_params = params
    if needs_pre:
        trace_bytes, orig_size = preprocess_image(
            image_bytes,
            upscale=upscale,
            blur=blur,
            sharpen=sharpness,
            remove_bg=remove_bg,
            trim=trim,
        )
        trace_params = _scale_params_for_upscale(params, upscale)
        suffix = ".png"

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        dst = Path(tmp) / "output.svg"
        src.write_bytes(trace_bytes)
        vtracer.convert_image_to_svg_py(str(src), str(dst), **trace_params)
        if opt != "none":
            optimize(dst, opt)
        svg = dst.read_text(encoding="utf-8")

    # Sau preprocess, ép width/height + viewBox về kích thước nội dung (đã trim).
    if orig_size is not None:
        svg = _normalize_svg_size(svg, orig_size[0], orig_size[1])

    report = dict(params)
    report["smoothing"] = smoothing
    report["upscale"] = upscale
    report["sharpness"] = sharpness
    report["remove_bg"] = remove_bg
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
        default=0,
        help="Độ rõ nét 0-250 (unsharp mask trước trace). 0 = tắt.",
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
