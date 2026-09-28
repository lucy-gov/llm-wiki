import pytest

from llm_wiki import bibtex
from llm_wiki.cli.bib import key_problem
from llm_wiki.errors import WikiError


def test_parse_values_macros_and_blocks():
    text = """
Stray text is a comment in BibTeX.
@comment{jabref-meta: whatever}
@preamble{"\\newcommand{\\x}{y}"}
@string{cdt = "California Department of Technology"}
@report{fx_cdt_plan_2025,
  title = {The {CDT} Plan: {Nested {Braces}}},
  institution = cdt # { Office},
  month = sep,
  year = 2025,
  note = "quoted {with} braces",
}
@article(fx_paren_2020, title = {Parenthesized})
"""
    entries = bibtex.parse(text)
    assert [(e.type, e.key) for e in entries] == [("report", "fx_cdt_plan_2025"), ("article", "fx_paren_2020")]
    f = entries[0].fields
    assert f["title"] == "The {CDT} Plan: {Nested {Braces}}"
    assert f["institution"] == "California Department of Technology Office"
    assert f["month"] == "9"
    assert f["year"] == "2025"
    assert f["note"] == "quoted {with} braces"
    assert entries[0].line == 6


def test_parse_error_is_readable():
    with pytest.raises(WikiError, match=r"x.bib:1: expected ',' or '}'"):
        bibtex.parse("@article{fx_a, title = {oops}", source="x.bib")
    with pytest.raises(WikiError, match=r"x.bib:2: unbalanced"):
        bibtex.parse("\n@article{fx_a, title = {oops", source="x.bib")


@pytest.mark.parametrize("raw, text", [
    (r"M{\"u}ller", "Müller"),
    (r"Garc\'{\i}a", "García"),
    (r"\v{S}koda", "Škoda"),
    (r"Data \& AI -- a {\emph{Review}}", "Data & AI – a Review"),
    (r"{\ss}tra{\ss}e 100\%", "ßtraße 100%"),
    (r"The {\textquoteleft}Open{\textquoteright} Agenda", "The ‘Open’ Agenda"),
])
def test_latex_to_text(raw, text):
    assert bibtex.latex_to_text(raw) == text


def test_split_names():
    assert bibtex.split_names("Smith, Avery and {Johnson and Johnson} AND Lee, J.") == [
        "Smith, Avery", "Johnson and Johnson", "Lee, J."
    ]
    assert bibtex.split_names("") == []


def test_split_files():
    assert bibtex.split_files("/z/storage/AAAA/a.pdf;/z/storage/BBBB/b.html") == [
        "/z/storage/AAAA/a.pdf", "/z/storage/BBBB/b.html"
    ]
    assert bibtex.split_files(r"/z/a\;b.pdf") == ["/z/a;b.pdf"]
    assert bibtex.split_files("Full Text:/z/a.pdf:application/pdf") == ["/z/a.pdf"]


@pytest.mark.parametrize("key, problem", [
    ("fx_smith_governance_2021", None),
    ("_" + "2026", "empty component"),
    ("fx__2026", "empty component"),
    ("2026", "no letters"),
    ("fx_a--b", "reserved"),
    ("fx:a", "unsafe"),
    ("", "empty"),
])
def test_key_problem(key, problem):
    result = key_problem(key)
    assert (result is None) if problem is None else (problem in result)
