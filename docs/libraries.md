# Libraries & dependencies

This project uses a small **required** Python stack for convert + web UI, plus optional engines for background removal, SVG optimization, analyze rasterization, ML landmarks, and Cloudflare deploy.

## Core Python (required)

Installed by `pip install -e .` / `pyproject.toml` `[project.dependencies]`.

| Library | Version pin | Used for | Where |
|---------|-------------|----------|--------|
| [**vtracer**](https://github.com/visioncortex/vtracer) | `0.6.*` | Raster → SVG vectorization | `image2svg.convert` |
| [**Pillow**](https://python-pillow.org/) | `>=10.0` | Image load/save, upscale, sharpen, trim, alpha | `convert`, `background`, `analyze` |
| [**pillow-heif**](https://github.com/bigcat88/pillow_heif) | `>=1.4.0` | HEIC/HEIF input support | `convert.pipeline` |
| [**PyYAML**](https://pyyaml.org/) | `>=6.0` | Load `recipes.yaml` | `convert` |
| [**scour**](https://github.com/scour-project/scour) | `>=0.38` | SVG optimize fallback (no Node/SVGO) | `convert.optimize` |
| [**FastAPI**](https://fastapi.tiangolo.com/) | `>=0.115` | Local HTTP API + UI routes | `image2svg.web` |
| [**Uvicorn**](https://www.uvicorn.org/) | `>=0.32` (`[standard]`) | ASGI server | `image2svg.web.app` |
| [**python-multipart**](https://github.com/Kludex/python-multipart) | `>=0.0.9` | Upload form parsing | FastAPI file endpoints |
| [**Pydantic**](https://docs.pydantic.dev/) | *(via FastAPI)* | Request body models | `web.app` |
| [**svg.path**](https://github.com/regebro/svg.path) | `>=6.0` | Parse SVG path geometry | `analyze` |
| [**NumPy**](https://numpy.org/) | `>=1.26` | Raster/skeleton math | `analyze.compiler` |
| [**PuLP**](https://coin-or.github.io/pulp/) | `>=2.8` | ILP part-label solver | `analyze.compiler.part_solver` |

Python standard library also used heavily: `argparse`, `pathlib`, `subprocess`, `tempfile`, `xml.etree.ElementTree`, `zipfile`, `threading`, `urllib`, etc.

## Dev Python (optional)

`pip install -e ".[dev]"`

| Library | Used for |
|---------|----------|
| [**pytest**](https://pytest.org/) | Unit tests |
| [**Ruff**](https://docs.astral.sh/ruff/) | Lint |

## SVG optimizer (external CLI, optional but recommended)

| Tool | How it is used | Notes |
|------|----------------|-------|
| [**SVGO**](https://github.com/svg/svgo) | `npx --yes svgo ...` after tracing | Needs **Node.js** / `npx` |
| **scour** | Pure-Python fallback | Already in core deps |

Detection order: SVGO (`npx`) → scour → skip optimize.

## Background removal (optional, lazy imports)

Not installed by default. Tried in order when `remove_bg=True`:

| Engine | Libraries / services | Env / notes |
|--------|----------------------|-------------|
| BiRefNet HTTP | stdlib `urllib` only | `IMAGE2SVG_BIREFNET_URL` |
| [**BEN2**](https://github.com/PramaLLC/BEN2) | `ben2`, [**PyTorch**](https://pytorch.org/) | Cached weights; `IMAGE2SVG_BEN2_ALLOW_DOWNLOAD=1` to fetch |
| [**rembg**](https://github.com/danielgatis/rembg) | `rembg` (+ ONNX models) | Prefers cached models; `IMAGE2SVG_REMBG_*` |
| Heuristic | Pillow only | Flood-fill from borders |

## Analyze raster helpers (optional system tools)

| Tool / lib | Used for |
|------------|----------|
| **rsvg-convert** (librsvg) | SVG → PNG evidence in analyze passes |
| **cairosvg** (optional pip) | Alternate SVG rasterize if installed |

## ML landmarks (optional, separate venv)

See `requirements-ml.txt` and `scripts/install-ml-deps.sh`. **Do not** `pip install -r requirements-ml.txt` blindly.

| Stack | Libraries | Purpose |
|-------|-----------|---------|
| Silhouette landmarks | Core package only | `--ml-landmarks` / `IMAGE2SVG_ML_LANDMARKS=1` |
| OpenMMLab pose | **PyTorch**, **mmcv**, **mmdet**, **mmpose**, **openmim** | Optional `--mmpose` |

Constraints: Python **3.10 or 3.11** for OpenMMLab; install torch before mmcv.

## Cloudflare Worker (optional Node stack)

`package.json` / `deployments/cloudflare/`

| Package | Used for |
|---------|----------|
| [**fflate**](https://github.com/101arrowz/fflate) | ZIP export in Worker |
| [**upng-js**](https://github.com/photopea/UPNG.js) | PNG decode/encode in Worker |
| [**Wrangler**](https://developers.cloudflare.com/workers/wrangler/) | Deploy / local Worker dev |

Cloudflare Images binding is used by the Worker for format transforms. This path does **not** run the full Python analyzer.

## Agent Skill packaging (optional tooling)

| Tool | Used for |
|------|----------|
| Node.js 18+ + npm | Publish/run `open-source-repo-skill` (`skills/installer`) |
| Python 3 (stdlib only) | Fallback installer `skills/installer/install.py` |

No extra Python packages are required to install the Agent Skill.

## License reminder

Upstream licenses differ (MIT, Apache-2.0, GPL-adjacent tools, model weights ToS, etc.). When redistributing binaries or hosted services, review each dependency and any downloaded model weights separately. This repo itself is **MIT** (see `LICENSE`).
