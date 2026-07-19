# Installing Agent Skills across tools

Agent Skills use a portable `SKILL.md` folder. Tools differ only by **search path**.

## Project vs global

| Scope | When to use |
|-------|-------------|
| Project | Team shares the skill with the repo (commit `.cursor/skills/...` etc.) |
| Global | Personal skill available in every repo |

## Paths by agent

| Agent | Project | Global |
|-------|---------|--------|
| Cursor | `.cursor/skills/<name>/` | `~/.cursor/skills/<name>/` |
| Claude Code | `.claude/skills/<name>/` | `~/.claude/skills/<name>/` |
| OpenAI Codex | `.codex/skills/<name>/` | `~/.codex/skills/<name>/` |
| Gemini CLI | `.gemini/skills/<name>/` | `~/.gemini/skills/<name>/` |
| Universal / others | `.agents/skills/<name>/` | `~/.agents/skills/<name>/` |

Cursor also discovers Claude/Codex skill dirs for compatibility.

## Commands (this repo)

From a clone:

```bash
# Project-local (all common agents)
node skills/installer/bin/install.mjs install

# Global (user home)
node skills/installer/bin/install.mjs install --global

# Subset
node skills/installer/bin/install.mjs install --agents cursor,claude
```

Via npm/npx (after publish, or from the installer folder):

```bash
cd skills/installer
npm install -g .

open-source-repo-skill install
open-source-repo-skill install --global --agents cursor,claude,codex,gemini
```

One-liner from the installer directory without global install:

```bash
npx --yes ./skills/installer install --global
```

## Invoke after install

- Cursor: `/open-source-repo` or ask “open-source this repo”
- Claude Code: `/open-source-repo`
- Codex / Gemini: mention the skill name or ask to apply **open-source-repo**

## Manual copy

If you cannot run the installer:

```bash
# Example: Cursor project skill
mkdir -p .cursor/skills
cp -R skills/open-source-repo .cursor/skills/open-source-repo
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .cursor\skills | Out-Null
Copy-Item -Recurse -Force skills\open-source-repo .cursor\skills\open-source-repo
```
