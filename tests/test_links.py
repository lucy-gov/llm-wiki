import json

from llm_wiki import wikilinks
from llm_wiki.cli import links


def parsed(text):
    return [(l.target, l.anchor, l.alias, l.line, l.embed, l.frontmatter) for l in wikilinks.links(text)]


def test_parse_forms():
    text = """---
parent: "[[wiki/agencies/cdt]]"
---
See [[wiki/sources/fx_a#C3|Smith 2021, C3]] and ![[wiki/concepts/x.md]].
| cell [[wiki/concepts/y\\|Y]] |
Inline `[[wiki/concepts/code]]` is ignored.
```
[[wiki/concepts/fenced]]
```
"""
    assert parsed(text) == [
        ("wiki/agencies/cdt", None, None, 2, False, True),
        ("wiki/sources/fx_a", "C3", "Smith 2021, C3", 4, False, False),
        ("wiki/concepts/x", None, None, 4, True, False),
        ("wiki/concepts/y", None, "Y", 5, False, False),
    ]


def test_headings():
    assert wikilinks.headings("## Claims\n### C3\n```\n### C9\n```\nText ^blk-1\n") == {"claims", "c3", "^blk-1"}


def write(vault, rel, text):
    path = vault.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build(vault):
    return links.build(vault)


def test_fixture_edges(vault):
    data = build(vault)
    cite = [e for e in data["edges"] if e["kind"] == "citation"]
    assert len(cite) == 1
    assert cite[0]["source"] == "wiki/concepts/data-governance"
    assert cite[0]["target"] == "wiki/sources/fx_smith_governance_2021"
    assert cite[0]["anchor"] == "C1" and cite[0]["anchor_resolved"] is True
    assert data["backlinks"]["wiki/sources/fx_smith_governance_2021"] == ["wiki/concepts/data-governance"]
    assert data["broken"] == [] and data["non_absolute"] == [] and data["orphans"] == []


def test_problems(vault):
    write(vault, "wiki/concepts/new.md", "\n".join([
        "[[wiki/sources/fx_smith_governance_2021#C9]]",   # bad anchor
        "[[wiki/concepts/unwritten-idea]]",               # broken: unwritten knowledge
        "[[concepts/data-governance]]",                   # shortest-path forms (acceptance 30)
        "[[data-governance]]",
        "[[wiki/../../etc/passwd]]",
        "[[research-restricted/transcripts/a]]",
    ]))
    data = build(vault)
    assert [e["anchor"] for e in data["bad_anchors"]] == ["C9"]
    broken = {e["target"] for e in data["broken"]}
    assert "wiki/concepts/unwritten-idea" in broken
    assert "research-restricted/transcripts/a" in broken
    non_abs = {e["target"]: e["suggestion"] for e in data["non_absolute"]}
    assert non_abs["concepts/data-governance"] == "wiki/concepts/data-governance"
    assert non_abs["data-governance"] == "wiki/concepts/data-governance"
    assert "wiki/concepts/unwritten-idea" not in non_abs
    assert "wiki/concepts/new" in data["orphans"]


def test_catalog_links_do_not_rescue_orphans(vault):
    write(vault, "wiki/concepts/lonely.md", "---\ntitle: Lonely\n---\n")
    write(vault, "wiki/concepts/index.md", "- [[wiki/concepts/lonely]]\n")
    assert "wiki/concepts/lonely" in build(vault)["orphans"]
    write(vault, "wiki/concepts/data-governance.md", "[[wiki/concepts/lonely]]\n")
    assert "wiki/concepts/lonely" not in build(vault)["orphans"]


def test_non_markdown_targets_resolve(vault):
    write(vault, "wiki/concepts/data-governance.md", "[[data/assessments.csv]]\n")
    assert build(vault)["broken"] == []


def test_main_writes_edges(vault, capsys):
    assert links.main([]) == 0
    assert json.loads((vault.root / "cache/edges.json").read_text())["counts"]["citations"] == 1
    assert "wrote cache/edges.json" in capsys.readouterr().out
