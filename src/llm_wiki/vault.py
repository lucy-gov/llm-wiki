"""The content repository as seen by the tools: layout, citekeys, and safe writes."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from llm_wiki.config import load_config
from llm_wiki.errors import WikiError
from llm_wiki.paths import guard_output, repo_root

WIKI_DIRS = (
    "sources", "agencies", "policies", "jurisdictions", "concepts",
    "methods", "debates", "timelines", "findings", "assessments",
)
CATALOG = "index.md"
OWN_PREFIX = "own:"
OWN_STEM_PREFIX = "own--"


def catalog_title(directory: str) -> str:
    return directory.replace("-", " ").capitalize()


def page_stem(citekey: str) -> str:
    """Filename stem of a source page: ``own:<name>`` becomes ``own--<name>``."""
    if citekey.startswith(OWN_PREFIX):
        return OWN_STEM_PREFIX + citekey.removeprefix(OWN_PREFIX)
    return citekey


def citekey_for_stem(stem: str) -> str:
    """Inverse of :func:`page_stem`. ``--`` is forbidden in citekeys, so this is unambiguous."""
    if stem.startswith(OWN_STEM_PREFIX):
        return OWN_PREFIX + stem.removeprefix(OWN_STEM_PREFIX)
    return stem


@dataclass
class Vault:
    """A content repository root. Every write goes through :meth:`write_text`."""

    root: Path

    @classmethod
    def find(cls, start: str | os.PathLike[str] | None = None) -> Vault:
        root = repo_root(start)
        if not (root / "wiki.toml").is_file():
            raise WikiError(f"{root} has no wiki.toml; run this from the content repository")
        return cls(root)

    @cached_property
    def config(self) -> dict[str, Any]:
        return load_config(self.root / "wiki.toml")

    @property
    def project_ids(self) -> list[str]:
        return [p["id"] for p in self.config["projects"]]

    @property
    def tag_deep(self) -> str:
        return self.config["tags"]["deep"]

    @property
    def tag_skip(self) -> str:
        return self.config["tags"]["skip"]

    # Layout
    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def wiki(self) -> Path:
        return self.root / "wiki"

    @property
    def sources(self) -> Path:
        return self.wiki / "sources"

    def source_page(self, citekey: str) -> Path:
        return self.sources / f"{page_stem(citekey)}.md"

    def text_cache(self, citekey: str) -> Path:
        return self.cache / "text" / f"{page_stem(citekey)}.txt"

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def wiki_dirs(self) -> list[str]:
        """The standard catalog directories, then any others present under ``wiki/``."""
        present = sorted(p.name for p in self.wiki.iterdir() if p.is_dir()) if self.wiki.is_dir() else []
        return [*WIKI_DIRS, *(d for d in present if d not in WIKI_DIRS and not d.startswith("."))]

    # Writes
    def write_text(self, path: Path, content: str) -> bool:
        """Atomically replace ``path`` inside the repository. Returns False if unchanged."""
        target = guard_output(path, self.root)
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return True

    def write_json(self, path: Path, data: Any) -> bool:
        return self.write_text(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")

    def read_json(self, path: Path, *, producer: str) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise WikiError(f"{self.rel(path)} does not exist; run {producer} first") from None
        except json.JSONDecodeError as exc:
            raise WikiError(f"{self.rel(path)} is corrupt ({exc}); rerun {producer}") from None
