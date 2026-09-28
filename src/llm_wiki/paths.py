"""Path guards shared by every tool.

No tool may take a path under the restricted vault as input, and no tool may
write outside the repository it was invoked from.
"""

from __future__ import annotations

import os
from pathlib import Path

from llm_wiki.errors import WikiError

RESTRICTED_MARKER = "research-restricted"


def is_restricted(path: str | os.PathLike[str]) -> bool:
    resolved = Path(path).expanduser().resolve()
    return any(RESTRICTED_MARKER in part for part in resolved.parts)


def guard_input(path: str | os.PathLike[str]) -> Path:
    """Resolve an input path, refusing anything inside the restricted vault."""
    if is_restricted(path):
        raise WikiError(
            f"refusing to read {path}: paths under {RESTRICTED_MARKER} are never "
            "read by main-side tools"
        )
    return Path(path).expanduser().resolve()


def repo_root(start: str | os.PathLike[str] | None = None) -> Path:
    """The nearest ancestor of ``start`` (default: cwd) containing ``.git``."""
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    raise WikiError(f"{here} is not inside a git repository")


def guard_output(path: str | os.PathLike[str], root: Path | None = None) -> Path:
    """Resolve an output path, refusing anything outside the invoking repository."""
    root = (root or repo_root()).resolve()
    resolved = Path(path).expanduser().resolve()
    if is_restricted(resolved):
        raise WikiError(f"refusing to write {path}: inside {RESTRICTED_MARKER}")
    if not resolved.is_relative_to(root):
        raise WikiError(f"refusing to write {path}: outside the repository at {root}")
    return resolved
