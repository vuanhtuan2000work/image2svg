"""Validate open-source-repo SKILL.md against Agent Skills conventions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "open-source-repo"
SKILL_MD = SKILL_DIR / "SKILL.md"
INSTALLER_SKILL = ROOT / "skills" / "installer" / "skill" / "SKILL.md"

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    assert match, "SKILL.md must start with YAML frontmatter delimited by ---"
    raw = match.group(1)
    data: dict[str, str] = {}
    current_key: str | None = None
    chunks: list[str] = []
    for line in raw.splitlines():
        if re.match(r"^[a-zA-Z0-9_-]+:\s*", line) and not line.startswith(" "):
            if current_key is not None:
                data[current_key] = "\n".join(chunks).strip().strip("\"'")
            key, _, rest = line.partition(":")
            current_key = key.strip()
            value = rest.strip()
            if value == ">" or value == "|":
                chunks = []
            elif value.startswith(">-") or value.startswith("|-"):
                chunks = []
            else:
                chunks = [value] if value else []
        else:
            chunks.append(line.strip())
    if current_key is not None:
        data[current_key] = "\n".join(chunks).strip().strip("\"'")
    return data


def test_skill_md_exists_and_folder_name_matches() -> None:
    assert SKILL_MD.is_file()
    assert SKILL_DIR.name == "open-source-repo"


def test_skill_frontmatter_required_fields() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    assert meta.get("name") == "open-source-repo"
    assert NAME_RE.match(meta["name"])
    description = meta.get("description", "")
    assert description
    assert len(description) <= 1024
    # Trigger terms for discovery
    lowered = description.lower()
    assert "open-source" in lowered or "open source" in lowered
    assert "cursor" in lowered or "claude" in lowered or "gemini" in lowered or "codex" in lowered


def test_skill_body_has_workflow_and_safe_non_goals() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    body = FRONTMATTER_RE.sub("", text, count=1)
    assert "Non-goals" in body
    assert "do not" in body.lower()
    assert "force-push" in body.lower() or "commit unless" in body.lower()
    assert "LICENSE" in body
    assert "CONTRIBUTING" in body
    assert len(body.splitlines()) < 500


def test_skill_references_exist_one_level_deep() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    refs = re.findall(r"\]\((references/[^)]+)\)", text)
    assert refs, "SKILL.md should link to references/"
    for rel in refs:
        path = SKILL_DIR / rel
        assert path.is_file(), f"Missing reference: {rel}"


def test_installer_skill_copy_matches_canonical() -> None:
    assert INSTALLER_SKILL.is_file(), "Run sync before publish: copy skills/open-source-repo -> skills/installer/skill"
    canonical = SKILL_MD.read_text(encoding="utf-8")
    packaged = INSTALLER_SKILL.read_text(encoding="utf-8")
    assert canonical == packaged


@pytest.mark.parametrize(
    "agent_dir",
    [
        ".cursor/skills/open-source-repo",
        ".claude/skills/open-source-repo",
        ".codex/skills/open-source-repo",
        ".gemini/skills/open-source-repo",
        ".agents/skills/open-source-repo",
    ],
)
def test_vendored_project_skills_present(agent_dir: str) -> None:
    skill = ROOT / agent_dir / "SKILL.md"
    assert skill.is_file(), f"Missing vendored skill at {agent_dir}"
    meta = _parse_frontmatter(skill.read_text(encoding="utf-8"))
    assert meta.get("name") == "open-source-repo"
