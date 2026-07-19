# Hướng dẫn sử dụng (Tiếng Việt)

**image2svg** chuyển ảnh (PNG/JPEG/WebP/…) sang SVG trên máy local, có CLI batch và Web UI.

Danh sách thư viện đầy đủ: [../libraries.md](../libraries.md).

Cài Agent Skill cho Cursor / Claude / Codex / Gemini: [../agent-skill.md](../agent-skill.md).

## Thư viện chính đã dùng

| Vai trò | Thư viện |
|---------|----------|
| Vector hóa ảnh → SVG | **vtracer** |
| Xử lý ảnh (upscale, nét, crop, alpha) | **Pillow**, **pillow-heif** |
| Đọc cấu hình recipe | **PyYAML** |
| Tối ưu SVG | **SVGO** (qua `npx`) hoặc **scour** |
| Web UI / API | **FastAPI**, **Uvicorn**, **python-multipart**, **Pydantic** |
| Phân tích SVG strip | **svg.path**, **NumPy**, **PuLP** |
| Xóa nền (tuỳ chọn) | BiRefNet HTTP / **BEN2**+**PyTorch** / **rembg** |
| Deploy Cloudflare (tuỳ chọn) | **fflate**, **upng-js**, **Wrangler** |

## Yêu cầu hệ thống

- Python **3.10+**
- (Khuyến nghị) Node.js để dùng **SVGO**
- Windows / macOS / Linux

## Cài đặt

```bash
git clone https://github.com/vuanhtuan2000work/image2svg.git
cd image2svg
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e .
```

Cài thêm công cụ dev:

```bash
pip install -e ".[dev]"
```

Kiểm tra SVGO:

```bash
npx svgo --version
```

## Chuẩn bị ảnh

```text
assets/raw/<loại_part>/*.png   →   assets/out/<loại_part>/*.svg
```

Ví dụ: `assets/raw/eye/eye_purple_01.png`

Tham số vtracer theo part nằm trong `configs/recipes.yaml`.

## Dùng CLI

```bash
# Chuyển toàn bộ folder trong assets/raw/
image2svg convert

# Chỉ một loại part
image2svg convert --part eye

# Tuỳ chọn chất lượng
image2svg convert --part eye --smoothing high --color-precision 8 --sharpness 80 --remove-bg --trim --overwrite
```

| Cờ | Ý nghĩa |
|----|---------|
| `--smoothing` | `none` / `low` / `medium` / `high` (upscale Lanczos trước khi trace) |
| `--color-precision` | 1–8 (cao = giữ nhiều màu hơn) |
| `--sharpness` | 0–250 (unsharp mask) |
| `--remove-bg` | Xóa nền → alpha trong suốt |
| `--trim` | Cắt sát nội dung |
| `--overwrite` | Ghi đè file SVG cũ |

## Dùng Web UI

```bash
image2svg serve
# hoặc
image2svg-server
```

- Convert: [http://127.0.0.1:8765](http://127.0.0.1:8765)
- Analyze: [http://127.0.0.1:8765/analyze](http://127.0.0.1:8765/analyze)

Kéo thả ảnh → chỉnh control → xem SVG → Export / tải file.

## Dùng Python API

```python
from pathlib import Path
from image2svg.convert import convert_image_bytes

data = Path("assets/raw/eye/eye_purple_01.png").read_bytes()
svg, params, optimizer, elapsed = convert_image_bytes(
    data,
    part="eye",
    smoothing="high",
    remove_bg=True,
    trim=True,
)

Path("out.svg").write_text(svg, encoding="utf-8")
print(optimizer, elapsed, params)
```

## Analyze / export manifest game

```bash
python scripts/export_game_manifest.py path/to/sheet.svg --dry-run
```

Chi tiết stack: [../animation-stack.md](../animation-stack.md).

## Biến môi trường hay dùng

| Biến | Mục đích |
|------|----------|
| `HOST` / `PORT` | Địa chỉ Web UI |
| `IMAGE2SVG_RECIPES` | Đường dẫn recipes tùy chỉnh |
| `IMAGE2SVG_ASSETS_ROOT` | Thư mục assets tùy chỉnh |
| `IMAGE2SVG_BIREFNET_URL` | Endpoint xóa nền BiRefNet |
| `IMAGE2SVG_ML_LANDMARKS` / `IMAGE2SVG_MMPOSE` | Bật ML khi analyze |

## Cloudflare (tuỳ chọn)

```bash
npm install
npm run deploy
```

Lưu ý: Worker chỉ làm convert nhẹ, **không** chạy full analyzer Python.

## Agent Skill (cho AI coding agents)

Cài skill **open-source-repo** để các agent open-source repo khác theo cùng chuẩn:

```bash
python skills/installer/install.py install --global
# hoặc (có Node): npx --yes ./skills/installer install --global
```

Trong chat agent: `/open-source-repo` hoặc hỏi “làm open source repo này”.

Chi tiết: [../agent-skill.md](../agent-skill.md).
