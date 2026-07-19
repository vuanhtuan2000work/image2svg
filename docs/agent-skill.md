# Agent Skill: open-source-repo

Portable [Agent Skills](https://agentskills.io/) package that teaches coding agents how to restructure a messy repo into open-source-ready layout (packages, LICENSE, docs, dependency map, multilingual usage).

Works with **Cursor**, **Claude Code**, **OpenAI Codex**, **Gemini CLI**, and any tool that loads `SKILL.md` from standard skill directories.

## What you get

| Path | Purpose |
|------|---------|
| `skills/open-source-repo/SKILL.md` | Canonical skill |
| `skills/open-source-repo/references/` | Layout + install + doc templates |
| `skills/installer/` | npm CLI (`open-source-repo-skill`) + Python fallback |

This repository vendors a **single canonical skill** plus two committed copies:

- `skills/open-source-repo/` (source of truth)
- `.agents/skills/open-source-repo/`
- `.cursor/skills/open-source-repo/`

Keep them aligned with:

```bash
python scripts/sync-agent-skills.py
```

Install into Claude / Codex / Gemini (or globally) with the installer below.

## Install into your machine / another project

### Option A — Python (no Node required)

```bash
# Project-local
python skills/installer/install.py install

# Global (all projects)
python skills/installer/install.py install --global

# Subset of agents
python skills/installer/install.py install --agents cursor,claude,codex,gemini
```

### Option B — npm / npx

**Prefer a trusted clone** (no registry trust required):

```bash
cd skills/installer
npm install -g .
open-source-repo-skill install
```

One-shot from repo root (Node 18+):

```bash
npx --yes ./skills/installer install
```

After publishing to npm, **pin the version** (do not use floating `@latest` for `--global`):

```bash
npx open-source-repo-skill@1.0.0 install
```

`--global` copies into `~/.<agent>/skills/` and affects **all** projects. Only use it when you trust the skill source. Prefer project-local install for reviews.

### Option C — manual copy

```bash
cp -R skills/open-source-repo .cursor/skills/open-source-repo
cp -R skills/open-source-repo .claude/skills/open-source-repo
cp -R skills/open-source-repo .codex/skills/open-source-repo
cp -R skills/open-source-repo .gemini/skills/open-source-repo
```

## Invoke

In chat:

```text
/open-source-repo
```

or natural language:

```text
Open-source this repository / làm open source repo này theo chuẩn OSS
```

## Pre-push / pre-publish gate (required)

Do **not** push or `npm publish` until this passes:

```bash
python scripts/prepublish-check.py
```

The gate verifies:

1. `SKILL.md` frontmatter (`name` + `description`) and safe non-goals
2. `skills/installer/skill/` matches canonical `skills/open-source-repo/`
3. Vendored copies exist for Cursor / Claude / Codex / Gemini / `.agents`
4. Pytest (skill + installer + core smoke tests)

Security notes before publish:

- Prefer install from a trusted clone (`python skills/installer/install.py` or `npx --yes ./skills/installer`)
- If using npm registry, **pin** `open-source-repo-skill@<version>`
- Treat `--global` as high-trust (writes into home skill dirs for all projects)

## Publish the npm package (maintainers)

```bash
python scripts/prepublish-check.py
node skills/installer/scripts/sync-skill.mjs   # if Node available
cd skills/installer
npm publish --access public
```

Package name: `open-source-repo-skill`.
