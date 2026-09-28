from pathlib import Path

import pytest

from llm_wiki.hooks import tools_repo

from conftest import REPO_ROOT


def check(files: dict[str, str]):
    return [v.rule for v in tools_repo.check(list(files), lambda p: files[p].encode())]


@pytest.mark.parametrize("path", ["wiki/sources/fx_a.md", "design/p1/thesis.md", "data/assessments.csv", "raw/zotero.bib"])
def test_root_research_paths_blocked(path):
    assert check({path: "x"}) == ["research-path"]


def test_fixture_vault_allowed():
    assert check({"tests/fixtures/vault/wiki/sources/fx_a.md": "citekey: fx_a\n"}) == []
    assert check({"tests/fixtures/vault/raw/zotero.bib": "@article{fx_a,\n}"}) == []


def test_bib_outside_fixtures_blocked():
    assert check({"docs/example.bib": "x"}) == ["bib"]


def test_unprefixed_citekeys_blocked_in_scope():
    real = "smith" + "_governance_2021"  # assembled so this file passes its own check
    assert check({"tests/test_x.py": f"citekey: {real}\n"}) == ["citekey"]
    assert check({"NOTES.md": f"[[wiki/sources/{real}#C3]]\n"}) == ["citekey"]
    assert check({"src/llm_wiki/cli/x.py": f"citekey: {real}\n"}) == []


@pytest.mark.parametrize("text", [
    "citekey: fx_a", "[[wiki/sources/own--memo_2026]]", "[@own:<name>]",
    "[[wiki/sources/<citekey>#C3]]", "[[wiki/sources/index|Sources]]", "cache/text/anything.txt",
])
def test_exempt_citekey_forms(text):
    assert tools_repo.unprefixed_citekeys(text) == []


@pytest.mark.parametrize("pattern", [
    "citekey: {k}", "[[wiki/sources/{k}]]", "@article{{{k},", "[@{k}, p. 1]", "cache/text/{k}.txt",
])
def test_every_citekey_form_detected(pattern):
    key = "doe" + "_x_2020"
    assert tools_repo.unprefixed_citekeys(pattern.format(k=key)) == [(1, key)]


def test_repository_is_clean():
    # Every citekey in scope is synthetic.
    problems = []
    files = list(REPO_ROOT.glob("*.md"))
    for scope in tools_repo.CITEKEY_SCOPES:
        files += [p for p in (REPO_ROOT / scope).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        problems += [(str(f.relative_to(REPO_ROOT)), *hit) for hit in tools_repo.unprefixed_citekeys(text)]
    assert problems == []
