from pathlib import Path

import pytest

from llm_wiki.hooks import content, denylist
from llm_wiki.hooks.patterns import Allowlist

NO_ALLOW = Allowlist(set(), set(), set())


def rules(repo, hashes=None, allow=NO_ALLOW):
    from llm_wiki.hooks import staged_paths

    return [v.rule for v in content.check(repo.root, staged_paths(), hashes, allow)]


@pytest.mark.parametrize("path", [
    "cache/text/anything.txt",
    "quarantine/2026-09-28/fx_a/input.pdf",
    "staging/wiki/sources/fx_a.md",
    "exports/instrument.md",
    "raw/attachments/fx_a.pdf",
])
def test_rule1_blocks_derived_paths_even_when_force_added(repo, path):
    # Force-adding past .gitignore is exactly the threat.
    repo.stage(".gitignore", "/cache/\n")
    repo.stage(path, "text", force=True)
    assert rules(repo) == ["1 blocked-path"]


def test_clean_page_passes(repo):
    repo.stage("wiki/concepts/x.md", "# Data governance\n\nOrdinary prose.\n")
    assert rules(repo) == []


def test_deletions_are_never_blocked(repo):
    repo.stage("cache/x.txt", "x", force=True)
    repo.git("commit", "-q", "--no-verify", "-m", "seed")
    repo.git("rm", "-q", "--cached", "cache/x.txt")
    assert rules(repo) == []


def test_rule2_restricted_string(repo):
    repo.stage("wiki/concepts/x.md", "see ../research-restricted/transcripts\n")
    repo.stage("CLAUDE.md", "Never read research-restricted.\n")
    assert rules(repo) == ["2 restricted"]


def test_rule3_denylist_blocks_participant_without_echoing_name(repo):
    hashes = frozenset({denylist.digest(denylist.normalize_name("Jordan Q. Example"))})
    repo.stage("wiki/findings/f.md", "A07 said, and Jordan Q. Example agreed.\n")
    violations = content.check(repo.root, ["wiki/findings/f.md"], hashes, NO_ALLOW)
    assert [v.rule for v in violations] == ["3 participant"]
    assert "Jordan" not in str(violations[0])


def test_rule3_email_and_phone_need_allowlist(repo):
    repo.stage("wiki/agencies/x.md", "Contact info@example.gov or (916) 555-0100.\n")
    assert sorted(rules(repo)) == ["3 email", "3 phone"]
    allow = Allowlist(set(), {"example.gov"}, {"9165550100"})
    assert rules(repo, allow=allow) == []


def test_allowlist_file_itself_is_exempt(repo):
    repo.stage(content.ALLOWLIST_FILE, "@example.gov\ninfo@example.org\n")
    assert rules(repo) == []


def test_rule4_secrets(repo):
    repo.stage("notes.md", "key: sk-ant-" + "a" * 40 + "\n")
    assert rules(repo) == ["4 secret"]


def test_rule5_size(repo):
    repo.stage("raw/docs/big.pdf", b"\0" * (content.MAX_BYTES + 1))
    assert rules(repo) == ["5 size"]


def test_binary_files_skip_text_rules(repo):
    repo.stage("raw/docs/x.pdf", b"\0research-restricted info@example.gov")
    assert rules(repo) == []


def test_main_warns_without_denylist(repo, tmp_path, capsys):
    repo.stage("wiki/concepts/x.md", "fine\n")
    assert content.main(["--denylist", str(tmp_path / "absent")]) == 0
    assert "no participant denylist" in capsys.readouterr().err


def test_main_blocks_with_denylist(repo, tmp_path, capsys):
    dl = tmp_path / "denylist"
    dl.write_text(denylist.digest("jordan example") + "\n")
    repo.stage("wiki/findings/f.md", "Jordan Example\n")
    assert content.main(["--denylist", str(dl)]) == 1
    assert "3 participant" in capsys.readouterr().err
