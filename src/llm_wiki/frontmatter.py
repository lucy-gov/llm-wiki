"""YAML frontmatter on markdown pages."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from llm_wiki.errors import WikiError

FENCE = "---"


def split(text: str) -> tuple[str | None, str, int]:
    """(raw frontmatter or None, body, number of lines the frontmatter block occupies)."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != FENCE:
        return None, text, 0
    for i in range(1, len(lines)):
        if lines[i].rstrip() in (FENCE, "..."):
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]), i + 1
    return None, text, 0


def parse(text: str, *, source: str = "<text>") -> tuple[dict[str, Any], str]:
    """(frontmatter mapping, body). A page with no frontmatter yields an empty mapping."""
    raw, body, _ = split(text)
    if raw is None:
        return {}, body
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise WikiError(f"{source}: invalid frontmatter: {exc}") from None
    if data is None:
        return {}, body
    if not isinstance(data, dict):
        raise WikiError(f"{source}: frontmatter is not a mapping")
    return data, body


def read(path: Path) -> tuple[dict[str, Any], str]:
    return parse(path.read_text(encoding="utf-8"), source=str(path))


def as_list(value: Any) -> list[str]:
    """A frontmatter list field, tolerating a bare scalar or null."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def as_date(value: Any) -> str | None:
    """An ISO date string from a YAML date, datetime, or string."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)
