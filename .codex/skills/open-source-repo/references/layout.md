# Recommended open-source layouts

## Python application / toolkit

```text
repo/
├── src/<package>/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── web/                 # if FastAPI/Flask UI
│   └── config/              # packaged defaults
├── configs/                 # editable checkout defaults
├── deployments/             # optional workers/docker
├── docs/
│   ├── libraries.md
│   └── usage/{vi,en,zh}.md
├── scripts/                 # thin wrappers only
├── tests/
├── assets/ or examples/     # samples, not secrets
├── skills/                  # optional Agent Skills
│   └── <skill-name>/SKILL.md
├── pyproject.toml
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
└── README.md
```

## JavaScript / TypeScript

```text
repo/
├── src/ or packages/
├── docs/
├── tests/ or *.test.ts
├── package.json
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

## Anti-patterns to fix

- Large unrelated scripts at repo root with no package
- README paths that do not exist
- Mixing personal game/sibling absolute paths into defaults without env overrides
- Committing `.venv/`, `node_modules/`, model weights, API keys
- Single-language docs only when the audience is mixed
