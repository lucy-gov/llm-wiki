"""wiki-links: parse every wikilink into cache/edges.json.

Citations are wikilinks into ``wiki/sources/``, so one edge table yields
backlinks, orphans, broken links (unwritten knowledge), unresolved heading
anchors such as a missing ``#C3``, and shortest-path links that are not
vault-absolute. This tool reports; lint decides what is an error.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llm_wiki import wikilinks
from llm_wiki.cli import parser, run
from llm_wiki.paths import RESTRICTED_MARKER
from llm_wiki.vault import CATALOG, Vault
from llm_wiki.version import tools_version

OUTPUT = "cache/edges.json"
SCANNED_DIRS = ("wiki", "design")
ROUTER = "index"
SOURCES_PREFIX = "wiki/sources/"


def page_id(vault: Vault, path: Path) -> str:
    return vault.rel(path).removesuffix(".md")


def is_catalog(pid: str) -> bool:
    return pid.startswith("wiki/") and pid.endswith("/" + CATALOG.removesuffix(".md"))


def scan_pages(vault: Vault) -> dict[str, Path]:
    pages: dict[str, Path] = {}
    router = vault.root / f"{ROUTER}.md"
    if router.is_file():
        pages[ROUTER] = router
    for d in SCANNED_DIRS:
        base = vault.root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if any(part.startswith(".") for part in path.relative_to(vault.root).parts):
                continue
            pages[page_id(vault, path)] = path
    return pages


class Resolver:
    def __init__(self, vault: Vault, pages: dict[str, Path]) -> None:
        self.root = vault.root
        self.pages = pages
        self.top = {p.name.removesuffix(".md") for p in vault.root.iterdir() if not p.name.startswith(".")}
        self._headings: dict[str, set[str]] = {}
        self.by_tail: dict[str, list[str]] = defaultdict(list)
        for pid in pages:
            parts = pid.split("/")
            for i in range(1, len(parts)):
                self.by_tail["/".join(parts[i:]).lower()].append(pid)

    def safe(self, target: str) -> bool:
        return bool(target) and not target.startswith("/") and ".." not in target.split("/") and RESTRICTED_MARKER not in target

    def absolute(self, target: str) -> bool:
        return self.safe(target) and target.split("/", 1)[0] in self.top

    def resolved(self, target: str) -> bool:
        if not self.safe(target):
            return False
        return target in self.pages or (self.root / target).is_file()

    def anchor_ok(self, target: str, anchor: str) -> bool:
        if target not in self.pages:
            return True
        if target not in self._headings:
            self._headings[target] = wikilinks.headings(self.pages[target].read_text(encoding="utf-8"))
        last = anchor.split("#")[-1]
        key = last if last.startswith("^") else wikilinks.normalize_anchor(last)
        return key in self._headings[target]

    def suggest(self, target: str) -> str | None:
        matches = self.by_tail.get(target.lower(), [])
        return matches[0] if len(matches) == 1 else None


def build(vault: Vault) -> dict[str, Any]:
    pages = scan_pages(vault)
    res = Resolver(vault, pages)
    edges: list[dict[str, Any]] = []
    for source, path in pages.items():
        for link in wikilinks.links(path.read_text(encoding="utf-8")):
            resolved = res.resolved(link.target)
            absolute = res.absolute(link.target)
            edge: dict[str, Any] = {
                "source": source,
                "target": link.target,
                "anchor": link.anchor,
                "alias": link.alias,
                "line": link.line,
                "kind": "citation" if link.target.startswith(SOURCES_PREFIX) and not is_catalog(link.target) else "link",
                "embed": link.embed,
                "frontmatter": link.frontmatter,
                "absolute": absolute,
                "resolved": resolved,
                "anchor_resolved": res.anchor_ok(link.target, link.anchor) if resolved and link.anchor else None,
            }
            if not absolute:
                edge["suggestion"] = res.suggest(link.target)
            edges.append(edge)

    backlinks: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["resolved"] and e["source"] != e["target"]:
            backlinks[e["target"]].add(e["source"])

    def inbound(pid: str) -> bool:
        return any(not is_catalog(s) for s in backlinks.get(pid, ()))

    orphans = [pid for pid in pages if pid != ROUTER and not is_catalog(pid) and not inbound(pid)]

    def where(e: dict[str, Any]) -> dict[str, Any]:
        return {"source": e["source"], "line": e["line"], "target": e["target"], "anchor": e["anchor"]}

    broken = [where(e) for e in edges if not e["resolved"]]
    bad_anchors = [where(e) for e in edges if e["anchor_resolved"] is False]
    non_absolute = [{**where(e), "suggestion": e["suggestion"]} for e in edges if not e["absolute"]]
    return {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "tools_version": tools_version(),
        "counts": {
            "pages": len(pages),
            "edges": len(edges),
            "citations": sum(e["kind"] == "citation" for e in edges),
            "broken": len(broken),
            "bad_anchors": len(bad_anchors),
            "non_absolute": len(non_absolute),
            "orphans": len(orphans),
        },
        "pages": list(pages),
        "edges": edges,
        "backlinks": {k: sorted(v) for k, v in sorted(backlinks.items())},
        "orphans": orphans,
        "broken": broken,
        "bad_anchors": bad_anchors,
        "non_absolute": non_absolute,
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = parser("wiki-links", "Parse wikilinks and citations into cache/edges.json.")
    p.add_argument("--json", action="store_true", help="print counts and problem lists as JSON")
    args = p.parse_args(argv)
    vault = Vault.find()
    data = build(vault)
    vault.write_json(vault.root / OUTPUT, data)

    if args.json:
        print(json.dumps({k: data[k] for k in ("counts", "orphans", "broken", "bad_anchors", "non_absolute")}, indent=2))
        return 0
    for e in data["non_absolute"]:
        hint = f"; did you mean [[{e['suggestion']}]]?" if e["suggestion"] else ""
        print(f"warning: {e['source']}.md:{e['line']}: [[{e['target']}]] is not a vault-absolute path{hint}", file=sys.stderr)
    for e in data["bad_anchors"]:
        print(f"warning: {e['source']}.md:{e['line']}: [[{e['target']}#{e['anchor']}]] has no such heading", file=sys.stderr)
    c = data["counts"]
    print(f"{c['pages']} pages, {c['edges']} links ({c['citations']} citations)")
    print(f"broken (unwritten): {c['broken']}; orphans: {c['orphans']}; bad anchors: {c['bad_anchors']}; non-absolute: {c['non_absolute']}")
    print(f"wrote {OUTPUT}")
    return 0


def cli() -> int:
    return run(main)
