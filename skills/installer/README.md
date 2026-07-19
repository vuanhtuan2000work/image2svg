# open-source-repo-skill

CLI to install the **open-source-repo** [Agent Skill](https://agentskills.io/) into Cursor, Claude Code, Codex, Gemini CLI, and `.agents/skills`.

## Install the skill (pick one)

### Python — no Node required (recommended fallback)

```bash
python skills/installer/install.py install
python skills/installer/install.py install --global
python skills/installer/install.py install --agents cursor,claude,codex,gemini
```

### From this repository with Node / npm

```bash
cd skills/installer
npm install -g .

open-source-repo-skill install
# or:
node skills/installer/bin/install.mjs install --global
npx --yes ./skills/installer install --global
```

### From npm (after publish) — pin the version

```bash
npm install -g open-source-repo-skill@1.0.0
npx open-source-repo-skill@1.0.0 install
```

Avoid unpinned `npx open-source-repo-skill install --global` — a compromised latest tarball would alter agent skills across every project.

## Use

```bash
# Project-local (recommended for teams — commit the copied skill dirs if you want)
open-source-repo-skill install

# User-global (all projects)
open-source-repo-skill install --global

# Only some agents
open-source-repo-skill install --agents cursor,claude,codex,gemini

# Inspect
open-source-repo-skill list
open-source-repo-skill path

# Remove
open-source-repo-skill uninstall --global
```

## After install

In the agent chat:

- `/open-source-repo`
- or: “open-source this repository” / “làm open source repo này”

## Skill source

Canonical skill lives at `../open-source-repo/` in the monorepo. The npm package ships a copy under `./skill/`.

Before publishing:

```bash
node skills/installer/scripts/sync-skill.mjs
npm publish --access public
```
