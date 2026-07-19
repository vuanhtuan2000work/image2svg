---
name: open-source-repo
description: >-
  Restructures messy repositories into open-source-ready layouts with src/
  packages, pyproject/package.json, LICENSE, CONTRIBUTING, SECURITY, multilingual
  usage docs, and a clear dependency map. Use when the user asks to open-source a
  project, clean repo structure for OSS, rewrite for GitHub standards, add OSS
  docs/skills, or make a codebase contributor-friendly across Cursor, Claude,
  Codex, or Gemini.
---

# Open-source a repository

Turn an ad-hoc codebase into a maintainable open-source project without changing core product behavior unless asked.

## When this skill applies

- "làm open source", "open-source this", "chuẩn OSS", "clean repo structure"
- Missing LICENSE / CONTRIBUTING / installable package entry points
- Flat scripts at repo root that should become a proper package
- Docs only in one language or outdated paths

## Non-goals

- Do not invent features unrelated to packaging/docs/structure
- Do not force-push, rewrite published history, or commit unless the user asks
- Do not download large ML weights or publish secrets

## Workflow checklist

Copy and track:

```text
OSS Progress:
- [ ] 1. Inventory languages, entry points, deps, secrets
- [ ] 2. Choose layout (src/ for Python; clear packages for JS/TS)
- [ ] 3. Move code into packages; keep thin root shims if needed
- [ ] 4. Add packaging metadata (pyproject.toml and/or package.json)
- [ ] 5. Add LICENSE, CONTRIBUTING, SECURITY, .gitignore
- [ ] 6. Rewrite README with install + quick start
- [ ] 7. Add multilingual usage docs + libraries map
- [ ] 8. Add minimal smoke tests
- [ ] 9. Verify install/run commands
- [ ] 10. Document agent skill install paths if shipping a skill
```

## Step 1 — Inventory

Identify:

1. Primary language(s) and runtime versions
2. Real entry points (CLI, server, library API)
3. Required vs optional dependencies (lazy-import heavies)
4. Hardcoded sibling paths / personal machine assumptions
5. Assets that should stay local vs ship in the repo

Read `references/layout.md` for recommended trees.

## Step 2 — Package layout

**Python default**

```text
src/<package>/
configs/                 # human-editable defaults
docs/usage/{vi,en,zh}.md
docs/libraries.md
tests/
scripts/                 # thin maintainer CLIs only
pyproject.toml
LICENSE
CONTRIBUTING.md
SECURITY.md
README.md
```

**JS/TS default**

```text
packages/ or src/
package.json (exports + bin)
docs/...
```

Rules:

- Prefer `from <package>...` imports after installable layout
- Root `convert.py` / `server.py`-style files become **deprecated shims** or are removed
- Configs live in `configs/` and/or package data; document env overrides

## Step 3 — Packaging metadata

Python (`pyproject.toml`):

- `[project]` name, version, description, requires-python, license, dependencies
- `[project.scripts]` console entry points
- `[project.optional-dependencies] dev`
- package-data for templates/static/config

Node (when relevant):

- clear `bin` / `exports`
- separate deploy packages (e.g. Cloudflare) under `deployments/`

## Step 4 — OSS docs (required set)

| File | Purpose |
|------|---------|
| `LICENSE` | Default MIT unless user specifies otherwise |
| `CONTRIBUTING.md` | Setup, layout, PR checklist |
| `SECURITY.md` | How to report issues |
| `README.md` | Install, quick start, library summary, links |
| `docs/libraries.md` | Full dependency map (required/optional) |
| `docs/usage/vi.md` + `en.md` (+ `zh.md` if useful) | How to use |

README must include:

1. One-line description
2. Links to multilingual usage guides
3. **Related libraries table** (name → role → required/optional)
4. Install + first command in < 30 seconds of reading
5. Env vars that matter

## Step 5 — Libraries documentation

In `docs/libraries.md`, group:

1. Core required runtime deps
2. Dev tooling
3. Optional engines (ML, rembg, remote APIs)
4. External CLIs (SVGO, system tools)
5. Deploy-only stacks (Workers, etc.)

For each row: **library**, **version pin if known**, **used for**, **where in code**.

Also put a short table in README and each `docs/usage/*.md`.

## Step 6 — Tests & verify

Minimum:

- Package imports after `pip install -e .` / `npm install`
- CLI `--help` works on Windows code pages (avoid fancy Unicode in help text)
- One test that configs/recipes/layout files resolve

## Step 7 — Ship as an Agent Skill (optional but preferred)

If the repo itself teaches a reusable workflow, publish under:

```text
skills/<skill-name>/SKILL.md
skills/installer/          # npm CLI that copies into agent dirs
```

Install targets (project-local and/or global):

| Agent | Project path | Global path |
|-------|--------------|-------------|
| Cursor | `.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| Codex | `.codex/skills/<name>/` | `~/.codex/skills/<name>/` |
| Gemini CLI | `.gemini/skills/<name>/` | `~/.gemini/skills/<name>/` |
| Universal | `.agents/skills/<name>/` | `~/.agents/skills/<name>/` |

Installer UX to support:

```bash
npx open-source-repo-skill install
npx open-source-repo-skill install --global
npx open-source-repo-skill install --agents cursor,claude,codex,gemini
```

After install, tell the user to invoke with `/open-source-repo` or ask: "open-source this repo".

Details: `references/agent-install.md`.

## Quality bar

Done means:

- New contributor can install and run from README alone
- Structure matches language ecosystem norms
- Docs list libraries honestly (required vs optional)
- No secret files committed
- Behavior preserved unless user requested changes

## Additional resources

- Layout templates: [references/layout.md](references/layout.md)
- Agent install paths: [references/agent-install.md](references/agent-install.md)
- Doc templates: [references/docs-templates.md](references/docs-templates.md)
