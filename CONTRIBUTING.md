# Contributing to image2svg

Thanks for helping improve the project. This document covers the minimal workflow expected for pull requests.

## Development setup

```bash
git clone https://github.com/vuanhtuan2000work/image2svg.git
cd image2svg
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

Optional SVG optimizer (recommended):

```bash
npx svgo --version
```

## Project layout

| Path | Purpose |
|------|---------|
| `src/image2svg/convert/` | Tracing, preprocess, recipes |
| `src/image2svg/background/` | Background-removal engine chain |
| `src/image2svg/analyze/` | Multi-pass SVG strip analyzer |
| `src/image2svg/web/` | FastAPI app + static UI |
| `configs/` | Checked-in recipe defaults (mirrors package config) |
| `deployments/cloudflare/` | Optional Cloudflare Worker deploy |
| `skills/open-source-repo/` | Portable Agent Skill (`SKILL.md`) |
| `skills/installer/` | npm + Python installer for Cursor/Claude/Codex/Gemini |
| `tests/` | Automated tests |
| `docs/` | Usage, libraries, agent-skill notes |

When editing the skill, update `skills/open-source-repo/` then sync:

```bash
python scripts/sync-agent-skills.py
python scripts/prepublish-check.py
```

See [docs/agent-skill.md](docs/agent-skill.md).

## Making changes

1. Create a focused branch from `master`.
2. Keep diffs small and related to one concern.
3. Prefer package imports (`from image2svg...`) — do not add new top-level scripts unless they are thin wrappers.
4. Update docs when CLI flags, env vars, or public APIs change.
5. Add or update tests under `tests/` when behavior changes.
6. If you edit recipes, keep `configs/recipes.yaml` and `src/image2svg/config/recipes.yaml` in sync.

## Checks before opening a PR

```bash
make ci
# or:
ruff check src tests scripts
pytest -q
python scripts/prepublish-check.py
python -m image2svg --help
```

Do not push when the gate fails. Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Pull request checklist

- [ ] Clear description of *why* the change is needed
- [ ] CLI / API / docs updated if user-facing
- [ ] No secrets, model weights, or large binary dumps committed
- [ ] Tests pass locally

## Code style

- Python 3.10+
- Imports at module top (no inline imports unless required for optional heavy deps)
- Prefer small, named functions over large scripts
- Optional ML / rembg / BEN2 imports stay lazy so the core package stays lightweight

## Reporting issues

Include:

- OS + Python version
- Exact command or API call
- Input sample (or a minimal reproduction)
- Full traceback / unexpected SVG output summary
