"""Leak-prevention hooks.

Hooks read staged content from the git index rather than the working tree, so
they check exactly what would be committed and can run either under the
pre-commit framework or as plain git hooks. Stdlib only, so the tools repo can
run its own hook from a source checkout.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"  {self.path}: [{self.rule}] {self.detail}"


def _git(*args: str, cwd: Path | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, check=True
    ).stdout


def staged_paths(cwd: Path | None = None) -> list[str]:
    """Paths added, copied, modified, or renamed in the index. Deletions are never blocked."""
    out = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", cwd=cwd)
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def staged_blob(path: str, cwd: Path | None = None) -> bytes:
    return _git("show", f":{path}", cwd=cwd)


def staged_size(path: str, cwd: Path | None = None) -> int:
    return int(_git("cat-file", "-s", f":{path}", cwd=cwd).decode().strip())


def as_text(blob: bytes) -> str | None:
    """Decoded text, or None for binary content (a NUL in the first 8 KB)."""
    if b"\0" in blob[:8192]:
        return None
    return blob.decode("utf-8", errors="replace")


def under(path: str, *prefixes: str) -> bool:
    """True when ``path`` is inside any root-relative directory in ``prefixes``."""
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def report(violations: Iterable[Violation], warnings: Iterable[str] = (), *, hook: str) -> int:
    violations = list(violations)
    for w in warnings:
        print(f"{hook}: warning: {w}", file=sys.stderr)
    if not violations:
        return 0
    print(f"{hook}: commit blocked ({len(violations)} problem(s)):", file=sys.stderr)
    for v in violations:
        print(v, file=sys.stderr)
    print("Fix the staged content rather than bypassing the hook.", file=sys.stderr)
    return 1
