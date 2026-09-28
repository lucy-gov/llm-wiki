"""Obsidian wikilink parsing.

``[[target#anchor|alias]]`` and ``![[embed]]``. Links inside fenced code blocks
and inline code spans are ignored; links in frontmatter are kept, since fields
such as ``derives_from`` and ``parent`` carry them.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from llm_wiki import frontmatter

_LINK = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")


@dataclass(frozen=True)
class Link:
    target: str
    anchor: str | None
    alias: str | None
    line: int
    embed: bool
    frontmatter: bool


def parse_inner(inner: str) -> tuple[str, str | None, str | None]:
    """Split ``target#anchor|alias``. ``\\|`` is the table-safe alias separator."""
    inner = inner.replace("\\|", "|")
    target, _, alias = inner.partition("|")
    target, _, anchor = target.partition("#")
    target = target.strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target, (anchor.strip() or None), (alias.strip() or None)


def links(text: str) -> Iterator[Link]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    _, _, fm_lines = frontmatter.split(text)
    fence: str | None = None
    for lineno, line in enumerate(text.split("\n"), start=1):
        in_fm = lineno <= fm_lines
        if not in_fm:
            m = _FENCE.match(line)
            if m:
                if fence is None:
                    fence = m.group(1)
                elif m.group(1) == fence:
                    fence = None
                continue
            if fence is not None:
                continue
            line = _CODE_SPAN.sub(lambda c: " " * len(c.group()), line)
        for m in _LINK.finditer(line):
            target, anchor, alias = parse_inner(m.group(2))
            yield Link(target, anchor, alias, lineno, m.group(1) == "!", in_fm)


def headings(text: str) -> set[str]:
    """Normalized heading texts and ``^block`` ids present in a page."""
    found: set[str] = set()
    fence: str | None = None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence:
            continue
        if h := re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line):
            found.add(normalize_anchor(h.group(1)))
        if b := re.search(r"\s\^([A-Za-z0-9-]+)\s*$", line):
            found.add("^" + b.group(1))
    return found


def normalize_anchor(anchor: str) -> str:
    return re.sub(r"\s+", " ", anchor).strip().lower()
