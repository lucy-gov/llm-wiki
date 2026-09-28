"""wiki-extract: source file → cache/text/<citekey>.txt.

PDFs are read with pypdf, pages separated by form feeds. Under 500 characters
triggers OCR through ``ocrmypdf`` when it is installed. HTML snapshots are
reduced to main-body text with trafilatura, and that text's hash is recorded
for change detection. A JSON sidecar next to the text records how it was made.
Failures that ingest should quarantine start with a reason code
(``no-source``, ``no-text``, ``unreadable``, ``unsupported``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from llm_wiki import frontmatter
from llm_wiki.cli import parser, run
from llm_wiki.errors import WikiError
from llm_wiki.paths import guard_input
from llm_wiki.text import PAGE_BREAK, body_hash, clean_extracted
from llm_wiki.vault import Vault
from llm_wiki.version import tools_version

BIB_JSON = "cache/bib.json"
MIN_PDF_CHARS = 500
PDF = (".pdf",)
HTML = (".html", ".htm", ".xhtml")
PLAIN = (".txt", ".md")
PREFERENCE = (*PDF, *HTML, *PLAIN)
OCR_TIMEOUT = 900


def _version(dist: str) -> str:
    try:
        return f"{dist} {metadata.version(dist)}"
    except metadata.PackageNotFoundError:
        return dist


def resolve_source(vault: Vault, entry: dict[str, Any]) -> Path:
    """The attachment to extract: the first existing PDF, then HTML, then plain text."""
    listed = entry.get("attachments") or []
    candidates = []
    for raw in listed:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = vault.raw / path
        path = guard_input(path)
        if path.is_file():
            candidates.append(path)
    ranked = sorted(
        (p for p in candidates if p.suffix.lower() in PREFERENCE),
        key=lambda p: PREFERENCE.index(p.suffix.lower()),
    )
    if ranked:
        return ranked[0]
    if candidates:
        raise WikiError(f"unsupported: no PDF, HTML, or text attachment among {', '.join(p.name for p in candidates)}")
    detail = f"listed attachments not found: {', '.join(listed)}" if listed else "the bib entry lists no attachment"
    raise WikiError(f"no-source: {detail}; pass --file to extract a specific file")


def pdf_text(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise WikiError(f"unreadable: {path.name} is encrypted")
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, OSError, ValueError, KeyError, TypeError) as exc:
        raise WikiError(f"unreadable: {path.name}: {exc}") from None
    return PAGE_BREAK.join(pages), len(pages)


def ocr_text(path: Path, scratch: Path) -> str | None:
    """Text from ocrmypdf's sidecar, or None if ocrmypdf is not installed."""
    exe = shutil.which("ocrmypdf")
    if exe is None:
        return None
    sidecar, out_pdf = scratch / "ocr.txt", scratch / "ocr.pdf"
    try:
        subprocess.run(
            [exe, "--force-ocr", "--quiet", "--sidecar", str(sidecar), str(path), str(out_pdf)],
            capture_output=True, text=True, check=True, timeout=OCR_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise WikiError(f"no-text: OCR failed on {path.name}: {exc.stderr.strip()[-500:]}") from None
    except subprocess.TimeoutExpired:
        raise WikiError(f"no-text: OCR timed out after {OCR_TIMEOUT}s on {path.name}") from None
    return sidecar.read_text(encoding="utf-8", errors="replace")


def html_text(path: Path) -> str:
    import trafilatura

    raw = path.read_bytes()
    for kwargs in ({"favor_precision": True}, {"favor_recall": True}):
        text = trafilatura.extract(
            raw, output_format="txt", include_comments=False, include_tables=True,
            include_images=False, include_links=False, deduplicate=False, **kwargs,
        )
        if text and text.strip():
            return text
    raise WikiError(f"no-text: no main-body text found in {path.name}")


def extract(vault: Vault, citekey: str, source: Path | None = None) -> dict[str, Any]:
    """Extract one source into the text cache. Returns the sidecar record."""
    entries = vault.read_json(vault.root / BIB_JSON, producer="wiki-bib")["entries"]
    if citekey not in entries:
        raise WikiError(f"{citekey!r} is not in {BIB_JSON}; rerun wiki-bib or check the key")
    path = guard_input(source) if source else resolve_source(vault, entries[citekey])
    if not path.is_file():
        raise WikiError(f"no-source: {path} does not exist")

    suffix = path.suffix.lower()
    record: dict[str, Any] = {"citekey": citekey, "source": str(path)}
    if suffix in PDF:
        text, pages = pdf_text(path)
        record.update(extractor=_version("pypdf"), pages=pages)
        if len(text.strip()) < MIN_PDF_CHARS:
            vault.cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=vault.cache, prefix=".ocr-") as scratch:
                ocr = ocr_text(path, Path(scratch))
            if ocr is None:
                raise WikiError(
                    f"no-text: {path.name} yielded {len(text.strip())} characters and ocrmypdf is not "
                    "installed (brew install ocrmypdf)"
                )
            if len(ocr.strip()) < MIN_PDF_CHARS:
                raise WikiError(f"no-text: {path.name} yielded {len(ocr.strip())} characters even after OCR")
            text = ocr
            record["extractor"] = f"{_version('ocrmypdf')} (OCR)"
    elif suffix in HTML:
        text = html_text(path)
        record.update(extractor=_version("trafilatura"), content_sha256=body_hash(text))
    elif suffix in PLAIN:
        text = path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".md":
            _, text = frontmatter.parse(text, source=str(path))
        record["extractor"] = "plain"
    else:
        raise WikiError(f"unsupported: cannot extract {path.suffix or 'extensionless'} files")

    text = clean_extracted(text)
    if not text.strip():
        raise WikiError(f"no-text: {path.name} is empty")
    record.update(
        chars=len(text),
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        extracted=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        tools_version=tools_version(),
    )
    out = vault.text_cache(citekey)
    vault.write_text(out, text)
    vault.write_json(out.with_suffix(".json"), record)
    record["text_cache"] = vault.rel(out)
    return record


def main(argv: Sequence[str] | None = None) -> int:
    p = parser("wiki-extract", "Extract a source's text into cache/text/ for reading and quote verification.")
    p.add_argument("citekey")
    p.add_argument("--file", type=Path, help="extract this file instead of the bib entry's attachment")
    args = p.parse_args(argv)
    vault = Vault.find()
    record = extract(vault, args.citekey, args.file)
    line = f"{record['text_cache']}: {record['chars']} characters via {record['extractor']}"
    if "content_sha256" in record:
        line += f"; content_sha256 {record['content_sha256']}"
    print(line)
    return 0


def cli() -> int:
    return run(main)
