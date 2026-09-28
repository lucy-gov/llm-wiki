import subprocess

import pytest

from llm_wiki.cli import init
from llm_wiki.errors import WikiError

from conftest import REPO_ROOT

CONFIG = REPO_ROOT / "tests/fixtures/vault/wiki.toml"
SHA = "0123456789abcdef0123456789abcdef01234567"


def test_content_repo_scaffold(tmp_path):
    target = tmp_path / "content"
    init.init_content(target, CONFIG, "https://example.invalid/llm-wiki", SHA)

    for path in ["CLAUDE.md", "README.md", "index.md", "log.md", "wiki.toml", ".gitignore",
                 ".pre-commit-config.yaml", "requirements.txt", "leak-allowlist.txt",
                 "wiki/sources/index.md", "design/p1-example/thesis.md", "data/assessments.csv",
                 "raw/notes/.gitkeep", ".claude/commands/.gitkeep", ".git"]:
        assert (target / path).exists(), path

    claude = (target / "CLAUDE.md").read_text()
    assert "{{" not in claude
    assert "| `p1` | Synthetic maturity instrument |" in claude
    assert f"@{SHA}" in (target / "requirements.txt").read_text()
    assert f"rev: {SHA}" in (target / ".pre-commit-config.yaml").read_text()


def test_content_repo_only_mentions_restricted_in_claude_md(tmp_path):
    target = tmp_path / "content"
    init.init_content(target, CONFIG, "https://example.invalid/llm-wiki", SHA)
    out = subprocess.run(["grep", "-rl", "--exclude-dir=.git", "research-restricted", str(target)], capture_output=True, text=True)
    assert [p.removeprefix(str(target) + "/") for p in out.stdout.split()] == ["CLAUDE.md"]


def test_restricted_scaffold(tmp_path):
    target = tmp_path / "research-restricted"
    init.init_restricted(target)
    assert (target / ".gitignore").exists()
    assert (target / "scripts/build-denylist.py").stat().st_mode & 0o111
    remotes = subprocess.run(["git", "-C", str(target), "remote"], capture_output=True, text=True).stdout
    assert remotes == ""
    # Only the contract, docs, and scripts are trackable.
    (target / "participants.csv").write_text("x")
    status = subprocess.run(["git", "-C", str(target), "status", "--porcelain", "-uall"], capture_output=True, text=True).stdout
    tracked = sorted(line[3:] for line in status.splitlines())
    assert tracked == [".gitignore", "BRIDGE.md", "CLAUDE.md", "README.md", "scripts/build-denylist.py"]


def test_restricted_name_required(tmp_path):
    with pytest.raises(WikiError, match="must contain"):
        init.init_restricted(tmp_path / "vault")


def test_refuses_nonempty_and_nested(tmp_path):
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "x").write_text("x")
    with pytest.raises(WikiError, match="not empty"):
        init.init_content(tmp_path / "full", CONFIG, "u", SHA)
    with pytest.raises(WikiError, match="inside the git repository"):
        init.init_content(REPO_ROOT / "tmp-nested", CONFIG, "u", SHA)


def test_config_validation(tmp_path):
    bad = tmp_path / "wiki.toml"
    bad.write_text('[[projects]]\nid = "P1"\nname = "x"\nkind = "y"\ndesign_dir = "z"\n')
    with pytest.raises(WikiError, match="lowercase"):
        init.load_config(bad)

def test_scaffolds_into_existing_clone_without_overwriting(tmp_path):
    target = tmp_path / "clone"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    (target / "README.md").write_text("mine\n")
    (target / ".gitignore").write_text("/cache/\n")

    skipped = init.init_content(target, CONFIG, "https://example.invalid/llm-wiki", SHA)

    assert sorted(skipped) == [".gitignore", "README.md"]
    assert (target / "README.md").read_text() == "mine\n"
    assert (target / "CLAUDE.md").exists()


def test_nested_path_inside_clone_refused(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path / "clone")], check=True)
    with pytest.raises(WikiError, match="inside the git repository"):
        init.init_content(tmp_path / "clone" / "sub", CONFIG, "u", SHA)


def test_restricted_vault_refuses_existing_repo(tmp_path):
    target = tmp_path / "research-restricted"
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    with pytest.raises(WikiError, match="created fresh"):
        init.init_restricted(target)
