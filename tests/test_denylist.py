import csv
import importlib.util
import sys

from llm_wiki.hooks import denylist
from llm_wiki.cli.init import templates


def load_vault_script():
    path = templates() / "restricted-vault" / "scripts" / "build-denylist.py"
    spec = importlib.util.spec_from_file_location("build_denylist", path)
    module = importlib.util.module_from_spec(spec)
    # Never leave bytecode in the template tree; wiki-init would copy it.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_normalization_matches_vault_script():
    script = load_vault_script()
    for s in ["José Ñúñez-O’Brien", "  JORDAN   q.  example ", "Zoë_Test", "Ｆｕｌｌｗｉｄｔｈ Name"]:
        assert script.normalize_name(s) == denylist.normalize_name(s)
    assert script.normalize_phone("+1 (916) 555-0100") == "9165550100"
    assert script.MAX_NGRAM == denylist.MAX_NGRAM


def test_end_to_end_vault_to_hook(tmp_path):
    script = load_vault_script()
    vault = tmp_path / "research-restricted"
    vault.mkdir()
    with (vault / "participants.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pseudonym", "full_name", "email", "phone", "agency_tier", "role_category", "interview_date"])
        w.writerow(["A07", "José Núñez", "JNunez@Example.org", "916-555-0100", "mid", "lead", "2026-10-01"])
    (vault / "denylist-extra.txt").write_text("# comment\nPat Third-Party\n")
    out = tmp_path / "denylist"
    hashes = script.collect(vault)
    out.write_text("\n".join(sorted(hashes)))
    loaded = denylist.load(out)

    assert denylist.hits("Interview with jose nunez today.", loaded)
    assert denylist.hits("Mail jnunez@example.org", loaded)
    assert denylist.hits("Call 916.555.0100", loaded)
    assert denylist.hits("PAT THIRD-PARTY", loaded)
    assert not denylist.hits("A07 described the reorganization.", loaded)


def test_missing_denylist_is_none(tmp_path):
    assert denylist.load(tmp_path / "absent") is None
