# image2svg

**Convert PNG/JPEG images to SVG locally** — offline raster-to-vector pipeline with batch CLI, live web UI, optional background removal, and per-part recipes.

[![CI](https://github.com/vuanhtuan2000work/image2svg/actions/workflows/ci.yml/badge.svg)](https://github.com/vuanhtuan2000work/image2svg/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![GitHub stars](https://img.shields.io/github/stars/vuanhtuan2000work/image2svg?style=social)](https://github.com/vuanhtuan2000work/image2svg/stargazers)

> Self-hosted **image to SVG** converter for game assets, icons, and chibi parts. No upload to a SaaS vectorizer — runs on your machine with [vtracer](https://github.com/visioncortex/vtracer) + optional SVGO.

<p align="center">
  <img src="assets/raw/eye/eye_purple_01.png" alt="PNG to SVG sample input — purple eye game asset before vectorization" width="220" />
</p>

<p align="center"><em>Sample input from <code>assets/raw/eye/</code> — drop your PNGs and batch-convert to SVG.</em></p>

## Why image2svg?

| You want… | image2svg gives you… |
|-----------|----------------------|
| **PNG → SVG** without cloud uploads | Fully **offline / local** pipeline |
| Fast iteration | **Web UI** on `localhost` + live preview |
| Hundreds of modular assets | **Batch CLI** + `recipes.yaml` per part type |
| Clean edges & transparent BG | Upscale smoothing, sharpen, **remove-bg**, trim |
| Game / Phaser workflows | Optional **SVG strip analyze** + manifest export |

**Not** another online “AI vectorizer.” Built for developers and asset pipelines who need repeatable, scriptable **raster to vector** conversion.

## Quick start (60 seconds)

```bash
git clone https://github.com/vuanhtuan2000work/image2svg.git
cd image2svg
python -m venv .venv

# Windows:  .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
image2svg serve
```

Open **http://127.0.0.1:8765** → drop a PNG → export SVG.

**CLI batch** (PNG folders → SVG):

```bash
# put files in assets/raw/<part>/*.png
image2svg convert --part eye --smoothing high --remove-bg --trim
# outputs: assets/out/eye/*.svg
```

**Python API:**

```python
from pathlib import Path
from image2svg.convert import convert_image_bytes

svg, *_ = convert_image_bytes(
    Path("assets/raw/eye/eye_purple_01.png").read_bytes(),
    part="eye",
    smoothing="high",
    remove_bg=True,
    trim=True,
)
Path("eye.svg").write_text(svg, encoding="utf-8")
```

## Features

| Feature | Description |
|---------|-------------|
| Local PNG/JPEG → SVG | Vectorize with vtracer; optional embedded-raster SVG mode |
| Batch asset folders | Mirror `assets/raw/<part>/` → `assets/out/<part>/` |
| Live web UI | Tune smoothing, color precision, sharpness, remove-bg, trim |
| Part recipes | Per-type presets in `configs/recipes.yaml` (eye, nose, body, …) |
| Background removal | BiRefNet / BEN2 / rembg / heuristic chain (optional) |
| SVG optimize | SVGO via `npx`, or Python scour fallback |
| Analyze mode | Multi-pass SVG strip compiler + game manifest helpers |
| Agent Skill | Portable `open-source-repo` skill for Cursor / Claude / Codex / Gemini |

## Demo controls (Web UI)

| Control | What it does |
|---------|----------------|
| Edge smoothness | Lanczos upscale before trace (cleaner edges) |
| Color accuracy | 1–8 bits/channel (higher = more colors) |
| Sharpness | Unsharp mask before vectorize |
| Remove background | Transparent alpha via engine chain |
| Trim padding | Crop to content / tight viewBox |

## Use cases

- **Game / VTuber / chibi modular assets** — eyes, mouths, limbs as separate SVGs  
- **Icon & sticker pipelines** — batch PNG packs → optimized SVG  
- **Privacy-sensitive art** — never upload source art to a hosted vectorizer  
- **CI / scripts** — call `image2svg` or `convert_image_bytes` from automation  

## Compare

| Tool | Offline | Batch folders | Local web UI | Recipes per part |
|------|---------|---------------|--------------|------------------|
| **image2svg** | Yes | Yes | Yes | Yes |
| Online AI vectorizers | No | Limited | Browser SaaS | No |
| Raw vtracer CLI alone | Yes | DIY | No | DIY |
| Illustrator / Inkscape | Yes | Manual | Desktop | Manual |

## Docs

| Language | Guide |
|----------|--------|
| English | [docs/usage/en.md](docs/usage/en.md) |
| Tiếng Việt | [docs/usage/vi.md](docs/usage/vi.md) |
| 中文 | [docs/usage/zh.md](docs/usage/zh.md) |
| Libraries | [docs/libraries.md](docs/libraries.md) |
| Animation / analyze | [docs/animation-stack.md](docs/animation-stack.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

## Requirements

- **Python 3.10+**
- Optional: **Node.js** for SVGO (`npx svgo`)
- Optional: Cairo / librsvg for some analyze raster paths

```bash
pip install -e ".[dev]"   # tests + lint
npx svgo --version        # recommended SVG optimizer
```

## Recipes (quality tuning)

Edit `configs/recipes.yaml`:

| Symptom | Try |
|---------|-----|
| Too many color shards | Raise `layer_difference`, lower `color_precision` |
| Lost highlights | Lower `filter_speckle`, raise `color_precision` |
| Over-rounded corners | Lower `corner_threshold` |
| Heavy paths | Lower `path_precision` (2–3 for chibi) |
| Single-color line art | `colormode: binary` |

## FAQ

**Is image2svg free and open source?**  
Yes — MIT license. Use it commercially; keep the license notice.

**Does it need the internet?**  
No for core convert. Optional engines (BEN2/rembg downloads, BiRefNet URL, Cloudflare deploy) may need network.

**PNG to SVG quality tips?**  
Start with `--smoothing high --color-precision 8 --trim`. Enable `--remove-bg` for cutout assets. Tune `recipes.yaml` per part type.

**Windows / macOS / Linux?**  
Yes. Activate the venv, then `image2svg serve` or `image2svg convert`.

**How is this different from Vectorizer.AI / similar SaaS?**  
Those are hosted. image2svg is **self-hosted**, scriptable, and built for **batch game/asset folders**.

**Can AI coding agents use this repo’s skill?**  
Yes — see [docs/agent-skill.md](docs/agent-skill.md) (`open-source-repo` skill for Cursor / Claude / Codex / Gemini).

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vuanhtuan2000work/image2svg&type=Date)](https://www.star-history.com/#vuanhtuan2000work/image2svg&Date)

## Project layout

```text
image2svg/
├── assets/raw/<part>/*.png   # your inputs
├── assets/out/<part>/*.svg   # outputs
├── configs/recipes.yaml      # vtracer presets
├── src/image2svg/            # installable Python package
├── docs/usage/               # EN / VI / ZH guides
└── skills/                   # optional Agent Skill pack
```

## Contributing

PRs welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).  
Security: [SECURITY.md](SECURITY.md).

```bash
python scripts/sync-agent-skills.py
python scripts/prepublish-check.py   # required before skill/publish changes
```

## License

[MIT](LICENSE) © image2svg contributors

## Acknowledgements

Built on [vtracer](https://github.com/visioncortex/vtracer), Pillow, FastAPI, SVGO/scour, and optional rembg / BEN2. Full map: [docs/libraries.md](docs/libraries.md).

---

<p align="center">
  <b>If image2svg saves you time, star the repo</b> — it helps others find a local PNG→SVG tool.<br/>
  Keywords: <code>png to svg</code> · <code>image to svg</code> · <code>raster to vector</code> · <code>offline vectorizer</code> · <code>batch svg converter</code>
</p>
