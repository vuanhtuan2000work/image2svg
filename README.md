# image2svg

[![CI](https://github.com/vuanhtuan2000work/image2svg/actions/workflows/ci.yml/badge.svg)](https://github.com/vuanhtuan2000work/image2svg/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.3.0-informational.svg)](CHANGELOG.md)

Local (offline) image → SVG pipeline powered by [vtracer](https://github.com/visioncortex/vtracer), with a batch CLI and a small FastAPI web UI.

**Core flow:** preprocess (optional upscale / sharpen / remove-bg / trim) → vectorize → optimize (SVGO or scour).

## Status

| Area | State |
|------|--------|
| Package | `pip install -e .` / `image2svg` CLI |
| Docs | EN / VI / ZH + [libraries map](docs/libraries.md) |
| Tests + CI | Pytest + Ruff + skill gate on 3.10–3.12 |
| Community | LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

## Documentation / Tài liệu

| Language | Usage guide |
|----------|-------------|
| Tiếng Việt | [docs/usage/vi.md](docs/usage/vi.md) |
| English | [docs/usage/en.md](docs/usage/en.md) |
| 中文 | [docs/usage/zh.md](docs/usage/zh.md) |

**Libraries used (full list):** [docs/libraries.md](docs/libraries.md)

**Agent Skill (Cursor / Claude / Codex / Gemini):** [docs/agent-skill.md](docs/agent-skill.md)

## Agent Skill — install once, use in any agent

This repo ships an [Agent Skills](https://agentskills.io/) playbook named **`open-source-repo`** so coding agents can open-source other projects the same way.

```bash
# Python (works without Node) — preferred
python skills/installer/install.py install          # this project
python skills/installer/install.py install --global # ALL projects (high trust)

# npm from this clone (Node 18+) — preferred over unpinned registry
npx --yes ./skills/installer install

# After npm publish: always pin the version
# npx open-source-repo-skill@1.0.0 install
```

Before push/publish, run the gate:

```bash
python scripts/prepublish-check.py
```

Then in Cursor / Claude / Codex / Gemini chat:

```text
/open-source-repo
```

or ask: `làm open source repo này` / `open-source this repository`.

Committed skill copies (kept in sync via `python scripts/sync-agent-skills.py`):

- `.agents/skills/open-source-repo/`
- `.cursor/skills/open-source-repo/`

For Claude / Codex / Gemini, run the installer above (or `--global`).

## Related libraries (quick view)

| Role | Library |
|------|---------|
| Vectorize image → SVG | [vtracer](https://github.com/visioncortex/vtracer) |
| Image processing | [Pillow](https://python-pillow.org/), [pillow-heif](https://github.com/bigcat88/pillow_heif) |
| Recipes config | [PyYAML](https://pyyaml.org/) |
| SVG optimize | [SVGO](https://github.com/svg/svgo) (`npx`) or [scour](https://github.com/scour-project/scour) |
| Web UI / API | [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), python-multipart, Pydantic |
| SVG strip analyze | [svg.path](https://github.com/regebro/svg.path), [NumPy](https://numpy.org/), [PuLP](https://coin-or.github.io/pulp/) |
| Remove background *(optional)* | BiRefNet HTTP / [BEN2](https://github.com/PramaLLC/BEN2)+PyTorch / [rembg](https://github.com/danielgatis/rembg) |
| Cloudflare Worker *(optional)* | [fflate](https://github.com/101arrowz/fflate), [upng-js](https://github.com/photopea/UPNG.js), [Wrangler](https://developers.cloudflare.com/workers/wrangler/) |

## Features

- Batch convert `assets/raw/<part>/*.png` → `assets/out/<part>/*.svg`
- Per-part recipes in `configs/recipes.yaml`
- Web UI for live preview and parameter tuning
- Optional SVG strip analyzer (`/analyze`) for game-manifest export
- Optional Cloudflare Worker deploy for a lighter hosted convert UI

## Repository layout

```text
image2svg/
├── configs/                 # Human-editable defaults (recipes)
├── deployments/cloudflare/  # Optional Worker
├── docs/                    # Usage, libraries, agent-skill
├── examples/                # Extra samples (optional)
├── scripts/                 # Maintainer utilities
├── skills/                  # Agent Skill + npm/python installer
│   ├── open-source-repo/    # SKILL.md (canonical)
│   └── installer/           # open-source-repo-skill CLI
├── src/image2svg/           # Installable Python package
│   ├── analyze/             # Multi-pass SVG strip compiler
│   ├── background/          # Background-removal engines
│   ├── convert/             # Trace + preprocess pipeline
│   ├── web/                 # FastAPI app + static UI
│   └── cli.py               # `image2svg` entry point
├── assets/                  # Local workspace for raw/out PNGs
└── tests/
```

## Requirements

- Python 3.10+
- Optional: Node.js (for SVGO via `npx`)
- Optional: system Cairo / librsvg for some analyze raster paths

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

Development extras:

```bash
pip install -e ".[dev]"
```

Check SVGO (recommended optimizer):

```bash
npx svgo --version
```

> `requirements.txt` remains as a thin pointer for older workflows. Prefer `pip install -e .`.

## Quick start

### CLI batch convert

```bash
# All part folders under assets/raw/
image2svg convert

# One part type
image2svg convert --part eye --smoothing high --color-precision 8 --sharpness 80 --remove-bg --trim

# Legacy form (still supported)
image2svg --part eye --overwrite
```

### Web UI

```bash
image2svg serve
# or
image2svg-server
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

Analyze UI: [http://127.0.0.1:8765/analyze](http://127.0.0.1:8765/analyze)

### Python API

```python
from image2svg.convert import convert_image_bytes

svg, params, optimizer, elapsed = convert_image_bytes(
    open("assets/raw/eye/eye_purple_01.png", "rb").read(),
    part="eye",
    smoothing="high",
    remove_bg=True,
    trim=True,
)
```

## Web UI controls

| Control | Effect | Backend |
|---------|--------|---------|
| Edge smoothness | Lanczos upscale before trace | `smoothing` |
| Color accuracy | Bits per channel (1–8) | `color_precision` |
| Sharpness | Unsharp mask (0–250) | `sharpness` |
| Remove background | Engine chain → transparent alpha | `remove_bg` |
| Trim padding | Crop to content / tight viewBox | `trim` |

## Recipes

Edit `configs/recipes.yaml` (mirrored in the package as `src/image2svg/config/recipes.yaml`).

| Symptom | Try |
|---------|-----|
| Too many color shards / broken gradients | Raise `layer_difference`, lower `color_precision` |
| Lost detail / highlights | Lower `filter_speckle`, raise `color_precision` |
| Over-rounded corners | Lower `corner_threshold` |
| Heavy paths | Lower `path_precision` (2–3 is usually enough) |
| Single-color line art | `colormode: binary` |

Override path with `IMAGE2SVG_RECIPES=/path/to/recipes.yaml`.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `HOST` / `PORT` | Web server bind address |
| `IMAGE2SVG_RECIPES` | Custom recipes YAML |
| `IMAGE2SVG_ASSETS_ROOT` | Custom assets root (contains `raw/` + `out/`) |
| `IMAGE2SVG_DATA_DIR` | Runtime data (correction memory, etc.) |
| `IMAGE2SVG_GAME_ROOT` | External game project root for manifest export |
| `IMAGE2SVG_ML_LANDMARKS` / `IMAGE2SVG_MMPOSE` | Optional analyze ML passes |
| `IMAGE2SVG_BIREFNET_URL` | Optional remote BiRefNet endpoint |
| `IMAGE2SVG_BEN2_ALLOW_DOWNLOAD` / `IMAGE2SVG_REMBG_ALLOW_DOWNLOAD` | Allow on-demand model downloads |

## Analyze + game export

See [docs/animation-stack.md](docs/animation-stack.md).

```bash
python scripts/export_game_manifest.py path/to/sheet.svg --dry-run
```

API: `POST /api/export-game-manifest`.

## Cloudflare deploy (optional)

```bash
npm install
npm run deploy
```

Worker source lives in `deployments/cloudflare/`. This path is a lighter convert UI and does not run the full Python analyzer.

## Background removal notes

When `--remove-bg` / UI toggle is on, engines are tried in order:

1. BiRefNet HTTP service (`IMAGE2SVG_BIREFNET_URL`)
2. Cached/local BEN2
3. Cached rembg
4. Heuristic flood-fill fallback

Heavy ML stacks are **not** installed by default. See comments in `requirements.txt` / `requirements-ml.txt`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).  
Security reports: [SECURITY.md](SECURITY.md).  
Release notes: [CHANGELOG.md](CHANGELOG.md).

Maintainer checks:

```bash
python scripts/sync-agent-skills.py
python scripts/prepublish-check.py
```

## License

[MIT](LICENSE)

## Acknowledgements

See [docs/libraries.md](docs/libraries.md) for the complete dependency map.

- [vtracer](https://github.com/visioncortex/vtracer) — vectorization
- Pillow / pillow-heif — image I/O and preprocess
- FastAPI / Uvicorn — local web UI
- SVGO / scour — SVG optimization
- svg.path, NumPy, PuLP — analyze pipeline
- Optional: rembg, BEN2, PyTorch, OpenMMLab (mmpose), Cloudflare Worker stack
