"""wiki-bib: parse the Zotero export and own notes into cache/bib.json.

Computes the derived sets every other stage reads: pending (no source page
yet), promotable (tagged deep but filed shallow), and degenerate keys (which
the researcher fixes in Zotero; this tool never invents a key).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from llm_wiki import bibtex, frontmatter
from llm_wiki.cli import parser, run
from llm_wiki.errors import WikiError
from llm_wiki.vault import CATALOG, OWN_PREFIX, Vault, citekey_for_stem
from llm_wiki.version import tools_version

BIB = "raw/zotero.bib"
NOTES = "raw/notes"
OUTPUT = "cache/bib.json"
ZOTERO_KEY_FIELDS = ("zotero_key", "zoterokey", "zotero-key")
_UNSAFE = re.compile(r"[\s/\\:#|\[\]^*?\"<>]")


def key_problem(key: str) -> str | None:
    """Why ``key`` cannot name a source page, or None if it is usable."""
    if not key:
        return "empty key"
    if "--" in key:
        return "contains '--', which is reserved for own: page filenames"
    if m := _UNSAFE.search(key):
        return f"contains {m.group()!r}, which is unsafe in filenames or wikilinks"
    if key[0] in "_-." or key[-1] in "_-." or "__" in key:
        return "has an empty component (missing author or title?)"
    if not re.search(r"[A-Za-z]", key):
        return "has no letters (missing author and title?)"
    return None


def zotero_entry(e: bibtex.Entry, vault: Vault) -> dict[str, Any]:
    f = e.fields
    tags = [t for t in (bibtex.latex_to_text(x) for x in f.get("keywords", "").split(",")) if t]
    date = f.get("year") or f.get("date", "")
    year = m.group() if (m := re.search(r"\d{4}", date)) else None
    return {
        "citekey": e.key,
        "namespace": "zotero",
        "type": e.type,
        "title": bibtex.latex_to_text(f.get("title", "")) or None,
        "authors": bibtex.split_names(f.get("author") or f.get("editor") or ""),
        "year": year,
        "doi": f.get("doi") or None,
        "url": f.get("url") or None,
        "attachments": bibtex.split_files(f.get("file", "")),
        "tags": tags,
        "projects": [t for t in tags if t in vault.project_ids],
        "deep": vault.tag_deep in tags,
        "skip": vault.tag_skip in tags,
        "zotero_key": next((f[k] for k in ZOTERO_KEY_FIELDS if f.get(k)), None),
        "origin": f"{BIB}:{e.line}",
    }


def note_entry(path, vault: Vault, warnings: list[str]) -> dict[str, Any]:
    rel = vault.rel(path)
    try:
        meta, _ = frontmatter.read(path)
    except WikiError as exc:
        warnings.append(str(exc))
        meta = {}
    tags = frontmatter.as_list(meta.get("tags"))
    projects = frontmatter.as_list(meta.get("projects"))
    for pid in projects:
        if pid not in vault.project_ids:
            warnings.append(f"{rel}: project {pid!r} is not declared in wiki.toml")
    date = frontmatter.as_date(meta.get("date")) or ""
    return {
        "citekey": OWN_PREFIX + path.stem,
        "namespace": "own",
        "type": "own-note",
        "title": str(meta.get("title") or path.stem),
        "authors": frontmatter.as_list(meta.get("authors")),
        "year": date[:4] or None,
        "doi": None,
        "url": None,
        "attachments": [path.relative_to(vault.raw).as_posix()],
        "tags": tags,
        "projects": [p for p in projects if p in vault.project_ids],
        "deep": vault.tag_deep in tags,
        "skip": vault.tag_skip in tags,
        "zotero_key": None,
        "origin": rel,
    }


def build(vault: Vault) -> dict[str, Any]:
    bib_path = vault.root / BIB
    try:
        text = bib_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WikiError(f"{BIB} not found; configure Better BibTeX to auto-export the library there") from None

    warnings: list[str] = []
    degenerate: list[dict[str, str]] = []
    entries: dict[str, dict[str, Any]] = {}

    def add(entry: dict[str, Any], key_to_check: str) -> None:
        key = entry["citekey"]
        if problem := key_problem(key_to_check):
            degenerate.append({"citekey": key, "reason": problem, "origin": entry["origin"]})
        elif key in entries:
            degenerate.append({"citekey": key, "reason": f"duplicate of {entries[key]['origin']}", "origin": entry["origin"]})
        else:
            entries[key] = entry

    for e in bibtex.parse(text, source=BIB):
        entry = zotero_entry(e, vault)
        if e.key.startswith(OWN_PREFIX):
            degenerate.append({"citekey": e.key, "reason": "the own: namespace is reserved for raw/notes/", "origin": entry["origin"]})
            continue
        add(entry, e.key)

    zotero_count = len(entries) + sum(1 for d in degenerate if d["origin"].startswith(BIB))
    recognized = {vault.tag_deep, vault.tag_skip, *vault.project_ids}
    if zotero_count and not any(recognized & set(e["tags"]) for e in entries.values()):
        warnings.append(
            f"no entry in {BIB} carries a recognized tag ({', '.join(sorted(recognized))}); "
            "check that Better BibTeX exports Zotero tags to `keywords`"
        )

    notes_dir = vault.root / NOTES
    if notes_dir.is_dir():
        for path in sorted(notes_dir.rglob("*.md")):
            add(note_entry(path, vault, warnings), path.stem)

    pending, promotable = [], []
    for key, entry in sorted(entries.items()):
        page = vault.source_page(key)
        if entry["skip"]:
            continue
        if not page.is_file():
            pending.append(key)
        elif entry["deep"]:
            try:
                meta, _ = frontmatter.read(page)
            except WikiError as exc:
                warnings.append(str(exc))
                continue
            if meta.get("depth") == "shallow":
                promotable.append(key)

    unmatched = []
    if vault.sources.is_dir():
        for page in sorted(vault.sources.glob("*.md")):
            if page.name != CATALOG and citekey_for_stem(page.stem) not in entries:
                unmatched.append(vault.rel(page))

    return {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "tools_version": tools_version(),
        "counts": {
            "entries": len(entries),
            "zotero": sum(e["namespace"] == "zotero" for e in entries.values()),
            "own": sum(e["namespace"] == "own" for e in entries.values()),
            "skipped": sum(e["skip"] for e in entries.values()),
            "pending": len(pending),
            "pending_deep": sum(entries[k]["deep"] for k in pending),
            "promotable": len(promotable),
            "degenerate": len(degenerate),
        },
        "pending": pending,
        "promotable": promotable,
        "degenerate": degenerate,
        "unmatched_pages": unmatched,
        "warnings": warnings,
        "entries": dict(sorted(entries.items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = parser("wiki-bib", "Parse raw/zotero.bib and raw/notes/ into cache/bib.json.")
    p.add_argument("--json", action="store_true", help="print counts and derived sets as JSON")
    args = p.parse_args(argv)
    vault = Vault.find()
    data = build(vault)
    vault.write_json(vault.root / OUTPUT, data)

    for w in data["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    for d in data["degenerate"]:
        print(f"warning: degenerate key {d['citekey']!r} at {d['origin']}: {d['reason']}; fix it in Zotero", file=sys.stderr)
    for page in data["unmatched_pages"]:
        print(f"warning: {page} has no bib entry (was its citekey changed?)", file=sys.stderr)

    if args.json:
        print(json.dumps({k: v for k, v in data.items() if k != "entries"}, indent=2))
        return 0
    c = data["counts"]
    print(f"{c['entries']} entries ({c['zotero']} Zotero, {c['own']} own), {c['skipped']} skipped")
    print(f"pending: {c['pending']} ({c['pending'] - c['pending_deep']} shallow, {c['pending_deep']} deep)")
    print(f"promotable: {c['promotable']}")
    print(f"degenerate keys: {c['degenerate']}")
    print(f"wrote {OUTPUT}")
    return 0


def cli() -> int:
    return run(main)
