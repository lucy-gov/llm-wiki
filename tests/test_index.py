import pytest

from llm_wiki.cli import index, init
from llm_wiki.errors import WikiError
from llm_wiki.vault import Vault

from conftest import FIXTURE_VAULT


def page(vault, rel, meta, body=""):
    path = vault.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{meta}\n---\n{body}")


def test_catalog_lines(vault):
    page(vault, "wiki/agencies/cdt.md", "type: agency\ntitle: California Department of Technology\nprojects: [p1, p2]\nupdated: 2026-09-01\nstub: true",
         "\n## Overview\n\nPlaceholder for [[wiki/agencies/cdt|CDT]]. More later.\n")
    page(vault, "wiki/agencies/broken.md", "title: [unclosed")
    result = index.build(vault)
    text = (vault.root / "wiki/agencies/index.md").read_text()
    assert "2 pages." in text
    assert ("- [[wiki/agencies/cdt|California Department of Technology]] (stub) — Placeholder for CDT. "
            "· p1, p2 · updated 2026-09-01") in text
    assert "- [[wiki/agencies/broken|broken]] — (invalid frontmatter)" in text
    assert result["warnings"] and "invalid frontmatter" in result["warnings"][0]
    # Source summaries come from the Gist.
    sources = (vault.root / "wiki/sources/index.md").read_text()
    assert "— Smith reports that agencies" in sources


def test_router_block_only(vault):
    index.build(vault)
    router = (vault.root / "index.md").read_text()
    assert "- [[wiki/sources/index|Sources]] (1)" in router
    assert "- [[wiki/concepts/index|Concepts]] (1)" in router
    assert router.startswith((FIXTURE_VAULT / "index.md").read_text().split("<!--")[0])
    assert index.build(vault)["changed"] == []  # idempotent


def test_router_without_markers(vault):
    (vault.root / "index.md").write_text("# Router\n")
    with pytest.raises(WikiError, match="no catalog block"):
        index.build(vault)


def test_router_cap(vault):
    (vault.root / "index.md").write_text("x\n" * 299 + index.BEGIN + "\n" + index.END + "\n")
    with pytest.raises(WikiError, match="over its 300-line cap"):
        index.build(vault)


def test_thousand_pages_router_stays_small(vault):
    """Acceptance test 16."""
    dirs = ["concepts", "agencies", "policies", "sources"]
    for i in range(1000):
        d = dirs[i % len(dirs)]
        stem = f"fx_page_{i:04d}" if d == "sources" else f"page-{i:04d}"
        page(vault, f"wiki/{d}/{stem}.md", f"type: x\ntitle: Page {i}", "\nBody.\n")
    result = index.build(vault)
    assert sum(result["counts"].values()) == 1002
    assert result["router_lines"] < 300
    assert "251 pages." in (vault.root / "wiki/concepts/index.md").read_text()


def test_works_on_wiki_init_output(tmp_path, monkeypatch):
    target = tmp_path / "content"
    init.init_content(target, FIXTURE_VAULT / "wiki.toml", "https://example.invalid/llm-wiki", "0" * 40)
    monkeypatch.chdir(target)
    result = index.build(Vault.find())
    assert len(result["counts"]) == 10 and sum(result["counts"].values()) == 0
    assert "- [[wiki/assessments/index|Assessments]] (0)" in (target / "index.md").read_text()
