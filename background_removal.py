"""Background removal engine chain with RGBA alpha cleanup."""

from __future__ import annotations

import os
import uuid
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


@dataclass(frozen=True)
class ComponentStats:
    label: int
    area: int
    x1: int
    y1: int
    x2: int
    y2: int
    cx: float
    cy: float

    @property
    def w(self) -> int:
        return self.x2 - self.x1 + 1

    @property
    def h(self) -> int:
        return self.y2 - self.y1 + 1


_BEN2_MODEL: object | None = None
_BEN2_DEVICE: object | None = None
_REMBG_SESSION: object | None = None
_REMBG_MODEL_NAME: str | None = None
_LAST_ENGINE = "none"


def get_last_background_engine() -> str:
    return _LAST_ENGINE


def remove_background(img: Image.Image, *, tolerance: int = 32) -> Image.Image:
    """Remove background using BiRefNet URL -> cached/local BEN2 -> cached rembg -> heuristic."""
    global _LAST_ENGINE
    source = img.convert("RGBA")
    _LAST_ENGINE = "none"
    for engine_name, engine in (
        ("birefnet", _remove_with_birefnet_service),
        ("ben2", _remove_with_ben2),
        ("rembg", _remove_with_rembg),
    ):
        try:
            result = engine(source)
        except Exception:
            result = None
        if result is not None:
            if not _LAST_ENGINE.startswith(f"{engine_name}:"):
                _LAST_ENGINE = engine_name
            return refine_alpha(result)
    _LAST_ENGINE = "heuristic"
    return refine_alpha(_remove_background_heuristic(source, tolerance=tolerance))


def refine_alpha(img: Image.Image) -> Image.Image:
    """Normalize to PNG-ready RGBA and clean semi-transparent edge noise."""
    img = img.convert("RGBA")
    alpha = img.getchannel("A")

    # Keep model feathering for fur/whiskers while removing only near-invisible noise.
    alpha = alpha.point(lambda p: 0 if p < 3 else 255 if p > 252 else p)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.18))
    alpha = _remove_distant_soft_alpha(alpha)

    img.putalpha(alpha)
    img = _keep_center_object_components(img)
    return img


def _remove_distant_soft_alpha(alpha: Image.Image) -> Image.Image:
    """Drop soft shadows/background haze that sits away from the solid object."""
    w, h = alpha.size
    confident = alpha.point(lambda p: 255 if p >= 96 else 0)
    grow_radius = max(4, min(18, int(max(w, h) * 0.025)))
    keep_zone = confident
    for _ in range(max(1, grow_radius // 4)):
        keep_zone = keep_zone.filter(ImageFilter.MaxFilter(size=9))

    alpha_data = alpha.tobytes()
    keep_data = keep_zone.tobytes()
    cleaned = bytes(
        0 if a < 72 and keep == 0 else a
        for a, keep in zip(alpha_data, keep_data, strict=False)
    )
    return Image.frombytes("L", (w, h), cleaned)


def _remove_with_birefnet_service(img: Image.Image) -> Image.Image | None:
    url = os.getenv("IMAGE2SVG_BIREFNET_URL") or os.getenv("BIREFNET_URL")
    if not url:
        return None

    body, content_type = _multipart_png_body(img, field_name=os.getenv("IMAGE2SVG_BIREFNET_FIELD", "file"))
    timeout = float(os.getenv("IMAGE2SVG_BIREFNET_TIMEOUT", "60"))
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": content_type, "Accept": "image/png,image/*,*/*"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return Image.open(BytesIO(payload)).convert("RGBA")


def _remove_with_ben2(img: Image.Image) -> Image.Image | None:
    model_id = os.getenv("IMAGE2SVG_BEN2_MODEL", "PramaLLC/BEN2")
    if not _ben2_model_available(model_id):
        return None

    try:
        import torch
        from ben2 import AutoModel
    except Exception:
        return None

    global _BEN2_DEVICE, _BEN2_MODEL
    if _BEN2_MODEL is None:
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
        model = AutoModel.from_pretrained(model_id)
        model.to(device).eval()
        _BEN2_MODEL = model
        _BEN2_DEVICE = device

    with torch.no_grad():
        foreground = _BEN2_MODEL.inference(img.convert("RGB"))  # type: ignore[union-attr]
    return foreground.convert("RGBA")


def _ben2_model_available(model_id: str) -> bool:
    """Avoid blocking local uploads by downloading BEN2 weights inside a request."""
    if _env_truthy("IMAGE2SVG_BEN2_ALLOW_DOWNLOAD"):
        return True

    model_path = Path(model_id).expanduser()
    if model_path.exists():
        return True

    if "/" not in model_id:
        return False

    cache_root = Path(
        os.getenv("HF_HOME")
        or os.getenv("HUGGINGFACE_HUB_CACHE")
        or (Path.home() / ".cache" / "huggingface")
    )
    hub_root = cache_root if cache_root.name == "hub" else cache_root / "hub"
    repo_cache = hub_root / f"models--{model_id.replace('/', '--')}"
    return any(repo_cache.glob("snapshots/*/model.safetensors"))


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _remove_with_rembg(img: Image.Image) -> Image.Image | None:
    try:
        from rembg import new_session, remove
    except Exception:
        return None

    global _LAST_ENGINE, _REMBG_MODEL_NAME, _REMBG_SESSION
    if _REMBG_SESSION is None:
        model_name = _select_rembg_model()
        if model_name is None:
            return None
        _REMBG_SESSION = new_session(model_name)
        _REMBG_MODEL_NAME = model_name

    result = remove(img.convert("RGBA"), session=_REMBG_SESSION)
    _LAST_ENGINE = f"rembg:{_REMBG_MODEL_NAME or 'unknown'}"
    if isinstance(result, Image.Image):
        return result.convert("RGBA")
    return Image.open(BytesIO(result)).convert("RGBA")


def _select_rembg_model() -> str | None:
    configured = os.getenv("IMAGE2SVG_REMBG_MODEL")
    candidates = [configured] if configured else ["birefnet-general", "isnet-general-use", "u2net"]
    for model_name in candidates:
        if model_name and _rembg_model_available(model_name):
            return model_name
    return None


def _rembg_model_available(model_name: str) -> bool:
    """Avoid model downloads in the request path unless explicitly allowed."""
    if _env_truthy("IMAGE2SVG_REMBG_ALLOW_DOWNLOAD"):
        return True

    model_path = Path(model_name).expanduser()
    if model_path.exists():
        return True

    cache_candidates = [
        Path.home() / ".u2net" / f"{model_name}.onnx",
        Path(os.getenv("U2NET_HOME", "")).expanduser() / f"{model_name}.onnx"
        if os.getenv("U2NET_HOME")
        else None,
    ]
    return any(path and path.exists() for path in cache_candidates)


def _multipart_png_body(img: Image.Image, *, field_name: str) -> tuple[bytes, str]:
    boundary = f"----image2svg-{uuid.uuid4().hex}"
    png = BytesIO()
    img.save(png, format="PNG")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="input.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + png.getvalue() + tail, f"multipart/form-data; boundary={boundary}"


def _detect_bg_color(img: Image.Image) -> tuple[int, int, int]:
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


def _remove_background_heuristic(img: Image.Image, *, tolerance: int = 32) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    bg = _detect_bg_color(img)
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
        if work.getpixel(seed) != sentinel:
            ImageDraw.floodfill(work, seed, sentinel, thresh=tolerance)

    diff = ImageChops.difference(work, Image.new("RGB", img.size, sentinel)).convert("L")
    bg_mask = diff.point(lambda p: 255 if p == 0 else 0)
    alpha = ImageChops.subtract(img.getchannel("A"), bg_mask)
    img.putalpha(alpha)
    return _keep_center_object_components(img)


def _label_alpha_components(img: Image.Image) -> tuple[list[int], list[ComponentStats]]:
    w, h = img.size
    alpha = img.getchannel("A")
    fg = [1 if v > 8 else 0 for v in alpha.getdata()]

    labels = [0] * (w * h)
    components: list[ComponentStats] = []
    current = 0
    for start in range(w * h):
        if fg[start] == 0 or labels[start] != 0:
            continue
        current += 1
        count = 0
        min_x = max_x = start % w
        min_y = max_y = start // w
        sum_x = 0
        sum_y = 0
        stack = [start]
        labels[start] = current
        while stack:
            idx = stack.pop()
            count += 1
            x, y = idx % w, idx // w
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            sum_x += x
            sum_y += y
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
        components.append(
            ComponentStats(
                label=current,
                area=count,
                x1=min_x,
                y1=min_y,
                x2=max_x,
                y2=max_y,
                cx=sum_x / max(count, 1),
                cy=sum_y / max(count, 1),
            )
        )
    return labels, components


def _component_center_score(component: ComponentStats, img_w: int, img_h: int, largest_area: int) -> float:
    center_x = (img_w - 1) / 2
    center_y = (img_h - 1) / 2
    diagonal = max(1.0, (img_w * img_w + img_h * img_h) ** 0.5)
    distance = ((component.cx - center_x) ** 2 + (component.cy - center_y) ** 2) ** 0.5
    center_score = 1.0 - min(1.0, distance / (diagonal * 0.5))
    area_score = min(1.0, component.area / max(largest_area, 1))
    edge_touch = (
        component.x1 <= 1
        or component.y1 <= 1
        or component.x2 >= img_w - 2
        or component.y2 >= img_h - 2
    )
    return area_score * 0.45 + center_score * 0.65 - (0.18 if edge_touch else 0.0)


def _component_gap(a: ComponentStats, b: ComponentStats) -> int:
    gap_x = max(0, max(a.x1, b.x1) - min(a.x2, b.x2) - 1)
    gap_y = max(0, max(a.y1, b.y1) - min(a.y2, b.y2) - 1)
    return max(gap_x, gap_y)


def _center_component_labels(
    components: list[ComponentStats],
    img_w: int,
    img_h: int,
    *,
    satellite_ratio: float = 0.015,
) -> set[int]:
    if not components:
        return set()

    largest_area = max(c.area for c in components)
    primary = max(
        components,
        key=lambda c: (_component_center_score(c, img_w, img_h, largest_area), c.area),
    )

    keep = {primary.label}
    max_gap = max(3, int(max(img_w, img_h) * 0.035))
    min_satellite_area = max(4, int(primary.area * satellite_ratio))
    max_center_distance = max(primary.w, primary.h, img_w, img_h) * 0.38

    for comp in components:
        if comp.label == primary.label or comp.area < min_satellite_area:
            continue
        gap = _component_gap(primary, comp)
        center_distance = ((comp.cx - primary.cx) ** 2 + (comp.cy - primary.cy) ** 2) ** 0.5
        if gap <= max_gap and center_distance <= max_center_distance:
            keep.add(comp.label)
    return keep


def _keep_center_object_components(img: Image.Image) -> Image.Image:
    """Keep the foreground object centered in the image and drop detached islands."""
    img = img.convert("RGBA")
    w, h = img.size
    labels, components = _label_alpha_components(img)

    if len(components) <= 1:
        return img

    keep = _center_component_labels(components, w, h)
    alpha = img.getchannel("A")
    old_alpha = list(alpha.getdata())
    new_alpha = bytes(old_alpha[i] if labels[i] in keep else 0 for i in range(w * h))
    img.putalpha(Image.frombytes("L", (w, h), new_alpha))
    return img
