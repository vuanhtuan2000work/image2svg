# Animation stack decision

## Context

`image2svg` analyzes **SVG frame strips** (PNG → vtracer → multi-frame sheet).
Target game: **feed-your-pet** — Phaser 3, `load.svg()` + per-frame **rect crop**, not bone deformation.

## Options compared

| Tool | Fit for this pipeline | Verdict |
|------|----------------------|---------|
| **Phaser frame manifest** (feed-your-pet) | Native format: `rect`, `contentRect`, frameRate | **Primary — use this** |
| **Compiler skeleton review** (`/analyze`) | QA overlay on strips before shipping to game | **Primary for validation** |
| **MMPose** (open-mmlab) | ML landmarks on **rendered PNG**; optional Phase 2 | Optional add-on |
| **DeepLabCut** | Train custom animal model; needs labeled video | Overkill for stylized SVG cats |
| **Spine runtimes** | Bone mesh animation runtime | **Not applicable** — game doesn't use Spine |
| **DragonBonesJS** | Same as Spine | **Not applicable** |

## Why not Spine / DragonBones?

- Game code: `PetScene.ts` → Phaser `Sprite` + `anims.create()` from **frame list**
- Assets: horizontal SVG strips (`1-Balinese-lengend.svg`, 4 frames)
- No `.skel`, no `.dbbin`, no slot/mesh attachment pipeline

Spine/DragonBones only make sense if you **change the game** to bone-deformed pets.

## Why not DeepLabCut / MMPose as primary?

- Input is **vector SVG paths**, not camera photos
- Stylized chibi cats have **fixed topology** — heuristic + medial-axis is enough for QA
- DLC/MMPose need PyTorch, GPU, training or heavy models
- Output is scientific keypoints, not Phaser `PetFrameAsset`

**When to add MMPose (Phase 2):** render each frame to PNG → run animal pose model → merge as extra `landmarkCandidates` in JSON.

## What we export now

Analyze JSON includes:

- `gameManifest` — Phaser-compatible frame rects (drop-in for `generate-cat-variants.mjs` workflow)
- `stackRecommendation` — documents this decision
- `frameAnalysis` — skeleton/landmarks for review UI

## Install notes (optional ML)

### Silhouette landmarks (works on Python 3.13, main `.venv`)

```bash
.venv/bin/python scripts/export_game_manifest.py sheet.svg --ml-landmarks
```

### MMPose (needs Python 3.10/3.11 — **not** 3.13)

**Do not** run `pip install -r requirements-ml.txt` directly. That tries to build `mmcv` from source before PyTorch and fails with:

`KeyError: '__version__'` / `Skip building ext ops due to the absence of torch`.

```bash
brew install uv
./scripts/install-ml-deps.sh

# then use the ML venv:
source .venv-ml/bin/activate
export IMAGE2SVG_MMPOSE_CONFIG=/path/to/config.py
export IMAGE2SVG_MMPOSE_CHECKPOINT=/path/to/checkpoint.pth
.venv-ml/bin/python scripts/export_game_manifest.py sheet.svg --ml-landmarks --mmpose
```

If Homebrew `python@3.11` fails with `ensurepip` / `pyexpat`, the script uses **uv** automatically. Manual repair:

```bash
brew install expat && brew reinstall python@3.11
/opt/homebrew/bin/python3.11 -c "import xml.parsers.expat; print('ok')"
```

Install order on **macOS ARM** (enforced by script):

**torch 2.1.2 → mmcv prebuilt wheel → chumpy → mmdet 3.2 → mmpose**

Do **not** use latest torch (2.12+) — OpenMMLab has no mmcv wheel for it and pip falls back to broken source build.

Default pipeline stays **lightweight Python** (numpy, svg.path, pulp optional).

## Game manifest export

Per-sheet JSON written to:

```
feed-your-pet/public/assets/pet/cat_actions/run/{folder}/analysis/{N}-{stem}.game-manifest.json
```

Merged overlay:

```
feed-your-pet/public/assets/pet/cat_actions/analysis/{variantId}.runFrameRects.json
```

`generate-cat-variants.mjs` prefers these rects over sharp auto-detect.

## Optional MMPose pass

1. Silhouette landmarks: `--ml-landmarks` or `IMAGE2SVG_ML_LANDMARKS=1` (no extra deps).
2. MMPose animal model: `./scripts/install-ml-deps.sh` (Python 3.11 venv) + config/checkpoint env vars + `--mmpose`.

Output field: `frameAnalysis[].mlLandmarks` merged into `landmarkCandidates` when enabled.
