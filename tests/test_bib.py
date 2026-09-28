import json

import pytest

from llm_wiki.cli import bib
from llm_wiki.errors import WikiError


def run(vault, capsys):
    assert bib.main([]) == 0
    out = capsys.readouterr()
    return json.loads((vault.root / "cache/bib.json").read_text()), out.err


def append_bib(vault, text):
    with (vault.root / "raw/zotero.bib").open("a") as f:
        f.write(text)


def test_fixture_sets(vault, capsys):
    data, err = run(vault, capsys)
    assert data["pending"] == ["fx_lao_governance_2026", "own:memo_governance_2026"]
    assert data["promotable"] == ["fx_smith_governance_2021"]
    assert data["degenerate"] == [] and data["unmatched_pages"] == [] and err == ""
    assert data["counts"]["skipped"] == 1
    assert "fx_skipped_press_2025" not in data["pending"]

    smith = data["entries"]["fx_smith_governance_2021"]
    assert smith["authors"] == ["Smith, Avery"]
    assert smith["tags"] == ["deep", "p1"] and smith["projects"] == ["p1"] and smith["deep"]
    assert smith["attachments"] == ["fx_smith_governance_2021.pdf"]

    memo = data["entries"]["own:memo_governance_2026"]
    assert memo["namespace"] == "own" and memo["year"] == "2026" and memo["projects"] == ["p1"]
    assert memo["attachments"] == ["notes/memo_governance_2026.md"]


def test_new_p1_item_is_pending(vault, capsys):
    """Acceptance test 1, first half."""
    append_bib(vault, "\n@report{fx_new_item_2026,\n  title = {New},\n  keywords = {p1},\n}\n")
    data, _ = run(vault, capsys)
    assert "fx_new_item_2026" in data["pending"]
    assert data["entries"]["fx_new_item_2026"]["projects"] == ["p1"]


def test_pending_deep_counted(vault, capsys):
    append_bib(vault, "\n@book{fx_deep_book_2024,\n  title = {Deep},\n  keywords = {deep, p1},\n}\n")
    data, _ = run(vault, capsys)
    assert "fx_deep_book_2024" in data["pending"]
    assert data["counts"]["pending_deep"] == 1


def test_degenerate_and_duplicate_keys_are_reported_not_invented(vault, capsys):
    bad = "_" + "2026"
    append_bib(vault, f"\n@misc{{{bad},\n  title = {{No author}},\n}}\n"
                      "\n@misc{fx_lao_governance_2026,\n  title = {Again},\n}\n")
    data, err = run(vault, capsys)
    reasons = {d["citekey"]: d["reason"] for d in data["degenerate"]}
    assert "empty component" in reasons[bad]
    assert "duplicate" in reasons["fx_lao_governance_2026"]
    assert bad not in data["entries"] and bad not in data["pending"]
    assert data["entries"]["fx_lao_governance_2026"]["title"] == "A Synthetic Review of State Data Governance"
    assert "fix it in Zotero" in err


def test_own_namespace_reserved_in_zotero(vault, capsys):
    append_bib(vault, "\n@misc{own:sneaky,\n  title = {x},\n}\n")
    data, _ = run(vault, capsys)
    assert data["degenerate"][0]["citekey"] == "own:sneaky"
    assert "own:sneaky" not in data["entries"]


def test_warns_when_no_recognized_tags(vault, capsys):
    (vault.root / "raw/zotero.bib").write_text("@article{fx_a_2020,\n  title = {A},\n  keywords = {unrelated},\n}\n")
    data, err = run(vault, capsys)
    assert "Better BibTeX exports Zotero tags" in err
    assert data["warnings"]


def test_unmatched_source_page(vault, capsys):
    page = vault.root / "wiki/sources/fx_renamed_2020.md"
    page.write_text("---\ntype: source\ntitle: x\n---\n")
    data, err = run(vault, capsys)
    assert data["unmatched_pages"] == ["wiki/sources/fx_renamed_2020.md"]
    assert "has no bib entry" in err


def test_missing_bib(vault):
    (vault.root / "raw/zotero.bib").unlink()
    with pytest.raises(WikiError, match="Better BibTeX"):
        bib.build(vault)


def test_requires_content_repo(tmp_path, monkeypatch, repo):
    with pytest.raises(WikiError, match="no wiki.toml"):
        bib.main([])
