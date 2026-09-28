"""Commit-msg hook: leak-prevention rule 6.

A commit staging any ``.gitignore`` must say ``[ignore-change]`` in its message.
This cannot be a pre-commit hook because the message does not exist yet then.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from llm_wiki.hooks import Violation, report, staged_paths
from llm_wiki.version import version_string

HOOK = "wiki-hook-commit-msg"
MARKER = "[ignore-change]"


def message_body(raw: str) -> str:
    """The message as git will record it: comment lines stripped."""
    return "\n".join(line for line in raw.splitlines() if not line.startswith("#"))


def check(paths: Sequence[str], message: str) -> list[Violation]:
    if MARKER in message_body(message):
        return []
    return [
        Violation(p, "6 ignore-change", f"editing .gitignore requires {MARKER} in the commit message")
        for p in paths
        if Path(p).name == ".gitignore"
    ]


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=HOOK, description="Require [ignore-change] for .gitignore edits.")
    p.add_argument("--version", action="version", version=version_string())
    p.add_argument("message_file", type=Path)
    args = p.parse_args(argv)
    message = args.message_file.read_text(encoding="utf-8", errors="replace")
    return report(check(staged_paths(), message), hook=HOOK)


if __name__ == "__main__":
    raise SystemExit(main())
