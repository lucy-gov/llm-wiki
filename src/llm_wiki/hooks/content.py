"""Content-repo pre-commit hook: leak-prevention rules 1–5."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from llm_wiki.hooks import (
    Violation,
    as_text,
    report,
    staged_blob,
    staged_paths,
    staged_size,
    under,
)
from llm_wiki.hooks import denylist
from llm_wiki.hooks.patterns import EMAIL, PHONE, Allowlist, find_secrets
from llm_wiki.paths import RESTRICTED_MARKER
from llm_wiki.version import version_string

HOOK = "wiki-hook-content"
BLOCKED_DIRS = ("cache", "quarantine", "staging", "exports", "raw/attachments")
RESTRICTED_EXEMPT = ("CLAUDE.md",)
MAX_BYTES = 5 * 1024 * 1024
ALLOWLIST_FILE = "leak-allowlist.txt"


def check(
    repo: Path,
    paths: Sequence[str],
    hashes: frozenset[str] | None,
    allow: Allowlist,
) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        # Rule 1: blocked regardless of .gitignore, since force-adds are the threat.
        if under(path, *BLOCKED_DIRS):
            violations.append(Violation(path, "1 blocked-path", "derived or scratch content never enters git"))
            continue

        # Rule 5.
        size = staged_size(path, cwd=repo)
        if size > MAX_BYTES:
            violations.append(Violation(path, "5 size", f"{size / 1024 / 1024:.1f} MB exceeds the 5 MB limit"))
            continue

        text = as_text(staged_blob(path, cwd=repo))
        if text is None:
            continue

        # Rule 2.
        if RESTRICTED_MARKER in text and path not in RESTRICTED_EXEMPT:
            violations.append(Violation(path, "2 restricted", f"mentions {RESTRICTED_MARKER}"))

        # Rule 3: participant identifiers, then contact details.
        if hashes:
            for label in denylist.hits(text, hashes):
                violations.append(Violation(path, "3 participant", f"denylisted identifier at {label}"))
        # The allowlist file is the one place public contact details are listed.
        if path != ALLOWLIST_FILE:
            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in EMAIL.finditer(line):
                    if not allow.allows_email(m.group()):
                        violations.append(Violation(path, "3 email", f"line {lineno}: {m.group()} (not in {ALLOWLIST_FILE})"))
                for m in PHONE.finditer(line):
                    if not allow.allows_phone(m.group()):
                        violations.append(Violation(path, "3 phone", f"line {lineno}: {m.group()} (not in {ALLOWLIST_FILE})"))

        # Rule 4.
        for name, redacted in find_secrets(text):
            violations.append(Violation(path, "4 secret", f"{name}: {redacted}"))
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=HOOK, description="Block leaks from the content repo.")
    p.add_argument("--version", action="version", version=version_string())
    p.add_argument("--denylist", type=Path, default=Path(os.environ.get("LLM_WIKI_DENYLIST", denylist.DEFAULT_PATH)))
    p.add_argument("files", nargs="*", help="ignored; staged files are read from the index")
    args = p.parse_args(argv)

    repo = Path.cwd()
    warnings = []
    hashes = denylist.load(args.denylist.expanduser())
    if hashes is None:
        warnings.append(
            f"no participant denylist at {args.denylist}; participant names are not being checked. "
            "Build it from inside the restricted vault with scripts/build-denylist.py."
        )
    allow = Allowlist.load(repo / ALLOWLIST_FILE)
    return report(check(repo, staged_paths(cwd=repo), hashes, allow), warnings, hook=HOOK)


if __name__ == "__main__":
    raise SystemExit(main())
