# Skills

| Skill | Installer | Docs |
|-------|-----------|------|
| [`open-source-repo`](./open-source-repo/) | [`installer/`](./installer/) | [docs/agent-skill.md](../docs/agent-skill.md) |

## Sync committed copies

```bash
python scripts/sync-agent-skills.py
```

This refreshes:

- `skills/installer/skill/` (npm package payload)
- `.agents/skills/open-source-repo/`
- `.cursor/skills/open-source-repo/`

## Install into more agents

```bash
python skills/installer/install.py install
python skills/installer/install.py install --global
```
