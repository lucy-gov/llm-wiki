"""Tools-repo pre-commit hook.

Blocks research content at the repository root, ``.bib`` files outside the
fixture tree, secrets, and citekeys lacking the reserved ``fx_`` prefix.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

from llm_wiki.hooks import Violation, as_text, report, staged_blob, staged_paths, under
from llm_wiki.hooks.patterns import find_secrets
from llm_wiki.version import version_string

HOOK = "wiki-hook-tools"
BLOCKED_ROOTS = ("wiki", "design", "data", "raw", "cache", "staging", "quarantine", "exports", "lint-reports")
FIXTURES = "tests/fixtures"
FIXTURE_PREFIX = "fx_"
# Directories whose citekeys must all be synthetic, in addition to root-level markdown.
CITEKEY_SCOPES = ("tests", "src/llm_wiki/templates")


def citekey_scope(path: str) -> bool:
    return under(path, *CITEKEY_SCOPES) or ("/" not in path and path.endswith(".md"))

_KEY = r"[A-Za-z0-9_:.-]+"
CITEKEY_PATTERNS = (
    re.compile(rf"wiki/sources/({_KEY})"),
    re.compile(rf"\bcitekey:[ \t]*[\"']?({_KEY})"),
    re.compile(rf"^[ \t]*@\w+\{{[ \t]*({_KEY})[ \t]*,", re.MULTILINE),
    re.compile(rf"\[@({_KEY})"),
    re.compile(rf"cache/text/({_KEY})\.txt"),
)
# Words that appear in citekey position in prose and templates but are not keys.
PLACEHOLDERS = {"anything", "citekey", "index", "key", "x"}


def _clean(key: str) -> str:
    key = key.rstrip(".")
    return key[:-3] if key.endswith(".md") else key


def citekeys(text: str) -> Iterator[tuple[int, str]]:
    """(line number, citekey) for every citekey-shaped reference in ``text``."""
    for pattern in CITEKEY_PATTERNS:
        for m in pattern.finditer(text):
            key = _clean(m.group(1))
            if key:
                yield text.count("\n", 0, m.start()) + 1, key


def unprefixed_citekeys(text: str) -> list[tuple[int, str]]:
    """Citekeys that are neither fixtures, own-namespace, nor placeholders."""
    found = set()
    for lineno, key in citekeys(text):
        if key.startswith((FIXTURE_PREFIX, "own:", "own--")) or key.lower() in PLACEHOLDERS:
            continue
        found.add((lineno, key))
    return sorted(found)


def check(paths: Sequence[str], read) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        in_fixtures = under(path, FIXTURES)
        if not in_fixtures and under(path, *BLOCKED_ROOTS):
            violations.append(Violation(path, "research-path", "research content belongs in the private content repo"))
            continue
        if path.endswith(".bib") and not in_fixtures:
            violations.append(Violation(path, "bib", f".bib files are only allowed under {FIXTURES}/"))
            continue

        text = as_text(read(path))
        if text is None:
            continue
        for name, redacted in find_secrets(text):
            violations.append(Violation(path, "secret", f"{name}: {redacted}"))
        if citekey_scope(path):
            for lineno, key in unprefixed_citekeys(text):
                violations.append(
                    Violation(path, "citekey", f"line {lineno}: {key!r} lacks the {FIXTURE_PREFIX} prefix; real citekeys never enter this repo")
                )
    return violations


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=HOOK, description="Keep research content out of the public tools repo.")
    p.add_argument("--version", action="version", version=version_string())
    p.add_argument("files", nargs="*", help="ignored; staged files are read from the index")
    p.parse_args(argv)
    repo = Path.cwd()
    return report(check(staged_paths(cwd=repo), lambda path: staged_blob(path, cwd=repo)), hook=HOOK)


if __name__ == "__main__":
    raise SystemExit(main())
