#!/usr/bin/env python3
"""Install open-source-repo Agent Skill without requiring Node.js."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

SKILL_NAME = "open-source-repo"

AGENTS = {
    "cursor": (".cursor", "skills", SKILL_NAME),
    "claude": (".claude", "skills", SKILL_NAME),
    "codex": (".codex", "skills", SKILL_NAME),
    "gemini": (".gemini", "skills", SKILL_NAME),
    "agents": (".agents", "skills", SKILL_NAME),
}


def skill_source() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "skill",
        here.parent / "open-source-repo",
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    raise SystemExit("Could not find open-source-repo/SKILL.md near the installer.")


def target_dir(agent: str, *, global_install: bool, cwd: Path) -> Path:
    parts = AGENTS[agent]
    root = Path.home() if global_install else cwd
    return root.joinpath(*parts)


def _assert_dest_contained(dest: Path, *, global_install: bool, cwd: Path) -> None:
    """Refuse writes outside the intended root (defense-in-depth)."""
    root = (Path.home() if global_install else cwd).resolve()
    resolved = dest.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"Refusing to write outside install root: {resolved} (root={root})") from exc


def copy_skill(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _skill_digest(src: Path) -> str:
    return hashlib.sha256((src / "SKILL.md").read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install open-source-repo Agent Skill")
    parser.add_argument("command", choices=["install", "uninstall", "list", "path"], nargs="?", default="install")
    parser.add_argument("--global", "-g", dest="global_install", action="store_true")
    parser.add_argument(
        "--agents",
        "-a",
        default=",".join(AGENTS),
        help="comma list: cursor,claude,codex,gemini,agents",
    )
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args(argv)

    src = skill_source()
    agents = [a.strip().lower() for a in args.agents.split(",") if a.strip()]
    cwd = Path(args.cwd).resolve()

    if args.command == "path":
        print(src)
        return 0

    for agent in agents:
        if agent not in AGENTS:
            raise SystemExit(f"Unknown agent: {agent}")

    if args.command == "list":
        for agent in agents:
            dest = target_dir(agent, global_install=args.global_install, cwd=cwd)
            mark = "x" if (dest / "SKILL.md").is_file() else " "
            print(f"[{mark}] {agent:8} {dest}")
        print(f"source: {src}")
        print(f"sha256: {_skill_digest(src)}")
        return 0

    if args.command == "install":
        if args.global_install:
            print(
                "[warn] --global installs into your home skill dirs and affects ALL projects. "
                "Prefer project-local install unless you trust this skill source.",
                file=sys.stderr,
            )
        digest = _skill_digest(src)
        for agent in agents:
            dest = target_dir(agent, global_install=args.global_install, cwd=cwd)
            _assert_dest_contained(dest, global_install=args.global_install, cwd=cwd)
            copy_skill(src, dest)
            print(f"installed -> {dest}")
        print(f"skill sha256: {digest}")
        print("\nDone. In your agent, run /open-source-repo or ask: open-source this repo")
        return 0

    if args.command == "uninstall":
        for agent in agents:
            dest = target_dir(agent, global_install=args.global_install, cwd=cwd)
            _assert_dest_contained(dest, global_install=args.global_install, cwd=cwd)
            if dest.exists():
                shutil.rmtree(dest)
                print(f"removed -> {dest}")
            else:
                print(f"missing  -> {dest}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
