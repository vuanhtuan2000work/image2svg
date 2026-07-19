# Usage guide (English)

**image2svg** is a local (offline) image → SVG pipeline with a batch CLI and a small web UI.

Full library list: [../libraries.md](../libraries.md).

Agent Skill for Cursor / Claude / Codex / Gemini: [../agent-skill.md](../agent-skill.md).

## Related libraries (summary)

| Role | Library |
|------|---------|
| Vectorize raster → SVG | **vtracer** |
| Image I/O & preprocess | **Pillow**, **pillow-heif** |
| Recipe config | **PyYAML** |
| SVG optimize | **SVGO** (`npx`) or **scour** |
| Web UI / API | **FastAPI**, **Uvicorn**, **python-multipart**, **Pydantic** |
| SVG strip analysis | **svg.path**, **NumPy**, **PuLP** |
| Background removal (optional) | BiRefNet HTTP / **BEN2**+**PyTorch** / **rembg** |
| Cloudflare deploy (optional) | **fflate**, **upng-js**, **Wrangler** |

## Requirements

- Python **3.10+**
- (Recommended) Node.js for **SVGO**
- Windows / macOS / Linux

## Install

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

Dev tools:

```bash
pip install -e ".[dev]"
```

Check SVGO:

```bash
npx svgo --version
```

## Prepare inputs

```text
assets/raw/<part_type>/*.png   →   assets/out/<part_type>/*.svg
```

Example: `assets/raw/eye/eye_purple_01.png`

Per-part vtracer parameters live in `configs/recipes.yaml`.

## CLI usage

```bash
# Convert every folder under assets/raw/
image2svg convert

# One part type
image2svg convert --part eye

# Quality flags
image2svg convert --part eye --smoothing high --color-precision 8 --sharpness 80 --remove-bg --trim --overwrite
```

| Flag | Meaning |
|------|---------|
| `--smoothing` | `none` / `low` / `medium` / `high` (Lanczos upscale before trace) |
| `--color-precision` | 1–8 (higher keeps more colors) |
| `--sharpness` | 0–250 (unsharp mask) |
| `--remove-bg` | Remove background → transparent alpha |
| `--trim` | Crop to content |
| `--overwrite` | Replace existing SVG files |

## Web UI

```bash
image2svg serve
# or
image2svg-server
```

- Convert: [http://127.0.0.1:8765](http://127.0.0.1:8765)
- Analyze: [http://127.0.0.1:8765/analyze](http://127.0.0.1:8765/analyze)

Drop an image, tune controls, preview SVG, then export/download.

## Python API

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

## Analyze / game manifest export

```bash
python scripts/export_game_manifest.py path/to/sheet.svg --dry-run
```

Stack notes: [../animation-stack.md](../animation-stack.md).

## Common environment variables

| Variable | Purpose |
|----------|---------|
| `HOST` / `PORT` | Web UI bind address |
| `IMAGE2SVG_RECIPES` | Custom recipes path |
| `IMAGE2SVG_ASSETS_ROOT` | Custom assets root |
| `IMAGE2SVG_BIREFNET_URL` | Remote BiRefNet remove-bg endpoint |
| `IMAGE2SVG_ML_LANDMARKS` / `IMAGE2SVG_MMPOSE` | Enable analyze ML passes |

## Cloudflare (optional)

```bash
npm install
npm run deploy
```

The Worker is a lighter convert UI and does **not** run the full Python analyzer.

## Agent Skill (for AI coding agents)

Install the **open-source-repo** skill so agents can open-source other repos with the same playbook:

```bash
python skills/installer/install.py install --global
# or (with Node): npx --yes ./skills/installer install --global
```

In agent chat: `/open-source-repo` or ask “open-source this repository”.

Details: [../agent-skill.md](../agent-skill.md).
