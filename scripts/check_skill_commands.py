"""Verify that CLI commands referenced by skill documentation exist."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from cli import build_parser

ROOT_DIR = Path(__file__).resolve().parent.parent
SKILL_FILES = (
    ROOT_DIR / "SKILL.md",
    *sorted((ROOT_DIR / "skills").glob("*/SKILL.md")),
    *sorted((ROOT_DIR / "references").glob("*.md")),
)
COMMAND_PATTERN = re.compile(r"scripts/cli\.py\s+([a-z][a-z-]*)")


def parser_commands(parser: argparse.ArgumentParser) -> set[str]:
    """Return the top-level subcommands registered by the CLI parser."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise RuntimeError("CLI parser does not define subcommands")


def referenced_commands(path: Path) -> set[str]:
    """Extract CLI subcommands used in command examples from one skill file."""
    return set(COMMAND_PATTERN.findall(path.read_text(encoding="utf-8")))


def main() -> int:
    available = parser_commands(build_parser())
    invalid: list[str] = []
    for path in SKILL_FILES:
        unknown = sorted(referenced_commands(path) - available)
        if unknown:
            invalid.append(f"{path.relative_to(ROOT_DIR)}: {', '.join(unknown)}")

    if invalid:
        print("Skill 文档引用了不存在的 CLI 子命令：", file=sys.stderr)
        print("\n".join(invalid), file=sys.stderr)
        return 1

    print(f"已验证 {len(SKILL_FILES)} 个 skill 文档的 CLI 命令引用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
