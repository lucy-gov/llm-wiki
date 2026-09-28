"""Resolve the tools version stamped into source pages and log.md.

The value is the short commit SHA the running code was built from, with
``-dirty`` appended when the install is editable or the working tree has
uncommitted changes. It is read from install metadata (PEP 610
``direct_url.json``), not from the content repo's requirements.txt, because an
editable install ignores the pin.
"""

from __future__ import annotations

import json
import subprocess
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

from llm_wiki import __version__

DIST_NAME = "llm-wiki"


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def _from_checkout(path: Path) -> str:
    """Version of a source checkout. Always -dirty: an editable install is unpinned."""
    sha = _git(path, "rev-parse", "--short=7", "HEAD")
    if sha is None:
        return "unknown-dirty"
    return f"{sha}-dirty"


def tools_version() -> str:
    """Short SHA, SHA-dirty, or 'unknown' when no provenance is recoverable."""
    try:
        dist = metadata.distribution(DIST_NAME)
    except metadata.PackageNotFoundError:
        # Running from a source tree without installing (e.g. PYTHONPATH=src).
        return _from_checkout(Path(__file__).resolve().parent)

    raw = dist.read_text("direct_url.json")
    if raw is None:
        return "unknown"
    info = json.loads(raw)

    vcs = info.get("vcs_info")
    if vcs and vcs.get("commit_id"):
        return vcs["commit_id"][:7]

    if info.get("dir_info", {}).get("editable"):
        parsed = urlparse(info.get("url", ""))
        if parsed.scheme == "file":
            return _from_checkout(Path(unquote(parsed.path)))
        return "unknown-dirty"

    return "unknown"


def pinnable_commit() -> str | None:
    """The full commit SHA of the running code, if it can be pinned.

    None for editable installs with uncommitted changes, and whenever no commit
    is recoverable: a dirty tree names no commit a pin could reproduce.
    """
    try:
        dist = metadata.distribution(DIST_NAME)
        raw = dist.read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        dist, raw = None, None
    if raw:
        info = json.loads(raw)
        if info.get("vcs_info", {}).get("commit_id"):
            return info["vcs_info"]["commit_id"]
        parsed = urlparse(info.get("url", ""))
        checkout = Path(unquote(parsed.path)) if parsed.scheme == "file" else None
    elif dist is None:
        checkout = Path(__file__).resolve().parent
    else:
        return None
    if checkout is None or _git(checkout, "status", "--porcelain"):
        return None
    return _git(checkout, "rev-parse", "HEAD")


def version_string() -> str:
    """The text printed by every tool's --version flag."""
    return f"llm-wiki {__version__} ({tools_version()})"
