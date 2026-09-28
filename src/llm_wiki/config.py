"""Instance configuration: the content repository's ``wiki.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from llm_wiki.errors import WikiError


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WikiError(f"no config at {path}; start from templates/wiki.toml.template") from None
    except tomllib.TOMLDecodeError as exc:
        raise WikiError(f"{path}: {exc}") from None
    projects = config.get("projects") or []
    if not projects:
        raise WikiError(f"{path}: declare at least one [[projects]] table")
    seen = set()
    for i, project in enumerate(projects, start=1):
        for field in ("id", "name", "kind", "design_dir"):
            if not str(project.get(field, "")).strip():
                raise WikiError(f"{path}: project {i} is missing `{field}`")
        pid = project["id"]
        if not pid.replace("-", "").isalnum() or pid.lower() != pid:
            raise WikiError(f"{path}: project id {pid!r} must be lowercase letters, digits, and hyphens")
        if pid in seen:
            raise WikiError(f"{path}: duplicate project id {pid!r}")
        seen.add(pid)
    config.setdefault("wiki", {}).setdefault("title", "Research Wiki")
    config.setdefault("tags", {}).setdefault("deep", "deep")
    config["tags"].setdefault("skip", "skip")
    design = config.setdefault("design", {})
    design.setdefault("indicator_domains", [])
    design.setdefault("module_domains", [])
    return config
