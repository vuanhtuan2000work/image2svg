# SVG Asset Pipeline

Pipeline local (offline) batch chuyển PNG → SVG cho thư viện asset modular.

**Bước 1–2 (tự động):** vtracer trace + SVGO/scour tối ưu  
**Bước 3 (thủ công):** gom layer, gradient, metadata/anchor — dùng `prompts/organize_svg.md` với GPT/Cursor

## Cấu trúc

```
svg-asset-pipeline/
  assets/
    raw/<part>/*.png    # input
    out/<part>/*.svg    # output sau trace + optimize
  recipes.yaml          # tham số vtracer theo part_type
  convert.py            # CLI chính
  prompts/
    organize_svg.md     # template bước 3
```

## Cài đặt

```bash
cd ~/Projects/svg-asset-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Tối ưu SVG:** ưu tiên SVGO qua `npx` (cần Node). Nếu không có Node, pipeline dùng `scour` (Python). Không có cả hai → bỏ qua optimize và in cảnh báo.

Kiểm tra SVGO:

```bash
npx svgo --version
```

## Web UI (preview + copy GPT)

```bash
source .venv/bin/activate
pip install -r requirements.txt   # nếu chưa cài fastapi/uvicorn
python server.py
```

Mở **http://127.0.0.1:8765** — kéo thả/chọn PNG, tinh chỉnh và xem SVG ngay trong trang. Mọi thay đổi control sẽ tự convert lại.

Controls:

| Control | Tác dụng | Backend |
|---------|----------|---------|
| **Độ mịn rìa** | Upscale + blur làm mượt cạnh | `smoothing` |
| **Màu sắc chuẩn xác** | Số bit màu/kênh (1–8, cao = nhiều màu hơn) | `color_precision` |
| **Độ rõ nét** | Unsharp mask trước trace (0–250) | `sharpness` |
| **Xóa nền** | Flood-fill từ viền → nền trong suốt; giữ vùng sáng bên trong object; lọc connected-component bỏ thanh/vụn rời rạc, chỉ giữ object chính | `remove_bg` |
| **Cắt padding** | Crop sát nội dung, viewBox ôm khít, không thừa lề | `trim` |

Nút **Export SVG** (góc phải panel output) và **Tải SVG** đều tải file `.svg`. **Copy prompt GPT** copy template bước 3 kèm SVG để dán vào ChatGPT/Cursor.

Tương đương CLI:

```bash
python convert.py --part eye --smoothing high --color-precision 8 --sharpness 80 --remove-bg --trim
```

## Analyze + game export (`/analyze`)

Màn **Analyze** (http://127.0.0.1:8765/analyze) chạy compiler 8-pass trên SVG frame strip: tách frame, scene graph, skeleton QA, temporal smoothing.

Output JSON gồm:

- `gameManifest` — frame rects tương thích **feed-your-pet** (Phaser 3 SVG sprite, không phải bone rig)
- `stackRecommendation` — lý do không dùng Spine/DragonBones; ML (MMPose/DeepLabCut) chỉ optional Phase 2

Chi tiết so sánh stack: [docs/ANIMATION_STACK.md](docs/ANIMATION_STACK.md)

### Export manifest sang feed-your-pet

```bash
# Ghi manifest vào game (mặc định ../game-2d/feed-your-pet)
.venv/bin/python scripts/export_game_manifest.py \
  ../game-2d/feed-your-pet/public/assets/pet/cat_actions/run/4-Balinese-lengend/1-Balinese-lengend.svg

# Bật ML landmarks (silhouette; thêm --mmpose nếu đã cài .venv-ml qua scripts/install-ml-deps.sh)
.venv/bin/python scripts/export_game_manifest.py path/to/sheet.svg --ml-landmarks

# Sau đó trong game repo:
cd ../game-2d/feed-your-pet && node scripts/generate-cat-variants.mjs
```

API: `POST /api/export-game-manifest` (form: `file`, optional `asset_path`, `game_root`, `ml_landmarks`, `mmpose`).

Biến môi trường: `IMAGE2SVG_GAME_ROOT`, `IMAGE2SVG_ML_LANDMARKS=1`, `IMAGE2SVG_MMPOSE=1`.

## Chạy pipeline CLI

```bash
source .venv/bin/activate

# Tất cả part trong assets/raw/
python convert.py

# Chỉ một loại part
python convert.py --part eye

# Ghi đè SVG đã có
python convert.py --part eye --overwrite
```

Output mirror cấu trúc `raw/`: `assets/raw/eye/foo.png` → `assets/out/eye/foo.svg`.

## Thêm part mới

1. Tạo folder `assets/raw/<part_type>/` và bỏ PNG vào.
2. Thêm block trong `recipes.yaml` → `parts.<part_type>` (override `default` nếu cần).
3. Chạy `python convert.py --part <part_type>`.

## Tinh chỉnh `recipes.yaml`

| Triệu chứng | Hướng xử lý |
|-------------|-------------|
| Quá nhiều mảnh màu / gradient vỡ | Tăng `layer_difference`, giảm `color_precision` |
| Mất chi tiết / highlight | Giảm `filter_speckle`, tăng `color_precision` |
| Bo tròn quá, mất góc nhọn | Giảm `corner_threshold` |
| File nặng, path dài | Giảm `path_precision` (2–3 đủ cho chibi) |
| Line-art 1 màu | `colormode: binary` |

Tham số vtracer hợp lệ: `colormode`, `hierarchical`, `mode`, `filter_speckle`, `color_precision`, `layer_difference`, `corner_threshold`, `length_threshold`, `max_iterations`, `splice_threshold`, `path_precision`.

**Lưu ý:** Python binding không có `gradient_step` — gom dải gradient bằng `layer_difference`.

## Làm mịn rìa (anti-aliasing)

vtracer trace thẳng trên ảnh nhỏ sẽ bám theo từng pixel → viền răng cưa. Pipeline
khắc phục bằng cách **CHỈ upscale ảnh (Lanczos) TRƯỚC khi trace** — Lanczos tự tạo cạnh
chuyển màu mượt ở RÌA nên vtracer fit spline cong, mà KHÔNG đụng tới màu/hình bên trong.
Output ép `viewBox` về kích thước gốc nên không phình file hiển thị.

| Mức | Upscale | Khi nào dùng |
|-----|---------|--------------|
| `none` | 1x | Line-art sắc, hoặc cần nhanh |
| `low` | 2x | Cân bằng, file nhỏ |
| `medium` (mặc định) | 3x | Hầu hết asset |
| `high` | 4x | Mịn rìa nhất |

**Quan trọng:** KHÔNG dùng GaussianBlur. Blur làm mịn cả vùng màu → méo hình, mất
highlight. Độ mịn rìa hoàn toàn đến từ upscale Lanczos. `filter_speckle` scale tuyến
tính theo `upscale` (không bình phương) để không xoá mất chi tiết nhỏ.

CLI: `python convert.py --part eye --smoothing high`. Web UI: chọn dropdown **Độ mịn rìa**.

## Bước 3 — tổ chức modular (thủ công)

1. Mở SVG trong `assets/out/`.
2. Copy nội dung vào `prompts/organize_svg.md` (phần placeholder).
3. Dán prompt vào GPT/Cursor — **không sửa geometry**, chỉ layer + gradient + metadata + anchors.

## Rủi ro / giới hạn

- vtracer tách theo **vùng màu**, không hiểu semantic iris/pupil/highlight → cần bước 3.
- Gradient gốc thành nhiều fill phẳng → bước 3 thay bằng `<radialGradient>` cho mượt và nhẹ hơn.
