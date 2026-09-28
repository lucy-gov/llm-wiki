import json
import stat

import pytest

from llm_wiki.cli import bib, extract
from llm_wiki.errors import WikiError

from conftest import make_pdf

LONG = "Across the sample, agencies reporting split CIO/program authority scored a full level lower on average. " * 6


def bib_with(vault, key, *, file=None, extra=""):
    field = f"  file = {{{file}}},\n" if file else ""
    with (vault.root / "raw/zotero.bib").open("a") as f:
        f.write(f"\n@online{{{key},\n  title = {{T}},\n  keywords = {{p1}},\n{field}{extra}}}\n")
    vault.write_json(vault.root / "cache/bib.json", bib.build(vault))


@pytest.fixture
def bibbed(vault):
    vault.write_json(vault.root / "cache/bib.json", bib.build(vault))
    return vault


def test_pdf_pages_and_sidecar(bibbed):
    make_pdf(bibbed.raw / "fx_smith_governance_2021.pdf", [LONG, "Page two (p. 2) text."])
    record = extract.extract(bibbed, "fx_smith_governance_2021")
    text = (bibbed.root / "cache/text/fx_smith_governance_2021.txt").read_text()
    assert "split CIO/program authority" in text
    assert text.count("\f") == 1 and "Page two (p. 2) text." in text.split("\f")[1]
    sidecar = json.loads((bibbed.root / "cache/text/fx_smith_governance_2021.json").read_text())
    assert sidecar["pages"] == 2 and sidecar["extractor"].startswith("pypdf")
    assert "content_sha256" not in sidecar
    assert record["text_cache"] == "cache/text/fx_smith_governance_2021.txt"


def test_short_pdf_without_ocrmypdf_is_no_text(bibbed, monkeypatch):
    make_pdf(bibbed.raw / "fx_smith_governance_2021.pdf", ["tiny"])
    cached = bibbed.root / "cache/text/fx_smith_governance_2021.txt"
    before = cached.read_text()
    monkeypatch.setattr(extract.shutil, "which", lambda _: None)
    with pytest.raises(WikiError, match=r"^no-text: .*brew install ocrmypdf"):
        extract.extract(bibbed, "fx_smith_governance_2021")
    assert cached.read_text() == before  # a failed extraction leaves the cache untouched


def test_short_pdf_uses_ocr(bibbed, monkeypatch, tmp_path):
    make_pdf(bibbed.raw / "fx_smith_governance_2021.pdf", ["tiny"])
    fake = tmp_path / "ocrmypdf"
    # Writes LONG to the --sidecar path.
    fake.write_text(f"#!/bin/sh\nwhile [ \"$1\" != --sidecar ]; do shift; done\nprintf '%s' '{LONG}' > \"$2\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(extract.shutil, "which", lambda _: str(fake))
    record = extract.extract(bibbed, "fx_smith_governance_2021")
    assert "(OCR)" in record["extractor"]
    assert not list((bibbed.cache).glob(".ocr-*"))


def test_corrupt_pdf_is_unreadable(bibbed):
    (bibbed.raw / "fx_smith_governance_2021.pdf").write_bytes(b"%PDF-1.4\nthis is not a pdf")
    with pytest.raises(WikiError, match=r"^(unreadable|no-text):"):
        extract.extract(bibbed, "fx_smith_governance_2021")


PAGE = """<html><head><title>Open Data</title><script>var t = "{stamp}";</script></head>
<body>
<header><div class="banner">{banner}</div><nav><a href="/">Home</a> | <a href="/about">About</a></nav></header>
<main><article>
<h1>Open Data Commitments</h1>
<p>The department publishes every non-confidential dataset on the state portal within ninety days of creation.</p>
<p>{body}</p>
</article></main>
<footer>Copyright 2026. Last generated {stamp}.</footer>
</body></html>"""


def snapshot(vault, banner="Flex alert today", body="Datasets are reviewed annually for quality.", stamp="1"):
    path = vault.raw / "attachments/fx_cdt_opendata_2026.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGE.format(banner=banner, body=body, stamp=stamp))
    return extract.extract(vault, "fx_cdt_opendata_2026")


def test_html_body_text_and_hash(vault):
    bib_with(vault, "fx_cdt_opendata_2026", file="attachments/fx_cdt_opendata_2026.html")
    first = snapshot(vault)
    text = (vault.root / "cache/text/fx_cdt_opendata_2026.txt").read_text()
    assert "within ninety days" in text
    assert "About" not in text and "Copyright" not in text
    assert first["content_sha256"]

    # Rotating banners and timestamps in chrome leave the hash alone (acceptance test 12, second half).
    assert snapshot(vault, banner="Wildfire smoke advisory", stamp="2")["content_sha256"] == first["content_sha256"]
    # A change to the body text changes it.
    assert snapshot(vault, body="Datasets are reviewed every five years.")["content_sha256"] != first["content_sha256"]


def test_prefers_pdf_over_snapshot(vault):
    bib_with(vault, "fx_both_2026", file="fx_both_2026.html;fx_both_2026.pdf")
    (vault.raw / "fx_both_2026.html").write_text("<p>x</p>")
    make_pdf(vault.raw / "fx_both_2026.pdf", [LONG])
    assert extract.extract(vault, "fx_both_2026")["extractor"].startswith("pypdf")


def test_own_note_strips_frontmatter(bibbed):
    extract.extract(bibbed, "own:memo_governance_2026")
    text = (bibbed.root / "cache/text/own--memo_governance_2026.txt").read_text()
    assert text.startswith("Synthetic researcher memo.")


def test_no_source(bibbed):
    with pytest.raises(WikiError, match=r"^no-source: listed attachments not found"):
        extract.extract(bibbed, "fx_smith_governance_2021")
    with pytest.raises(WikiError, match=r"^no-source: the bib entry lists no attachment"):
        extract.extract(bibbed, "fx_lao_governance_2026")


def test_unknown_key_and_missing_bib_json(vault):
    with pytest.raises(WikiError, match="run wiki-bib first"):
        extract.extract(vault, "fx_lao_governance_2026")
    vault.write_json(vault.root / "cache/bib.json", bib.build(vault))
    with pytest.raises(WikiError, match="not in cache/bib.json"):
        extract.extract(vault, "fx_nope_2020")


def test_refuses_restricted_file(bibbed, tmp_path):
    secret = tmp_path / "research-restricted" / "transcripts" / "a.txt"
    secret.parent.mkdir(parents=True)
    secret.write_text("x")
    with pytest.raises(WikiError, match="never read"):
        extract.extract(bibbed, "fx_lao_governance_2026", secret)
