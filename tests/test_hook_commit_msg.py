from llm_wiki.hooks import commit_msg


def test_gitignore_change_needs_marker(repo, tmp_path):
    repo.stage(".gitignore", "/cache/\n")
    msg = tmp_path / "MSG"
    msg.write_text("Tweak ignores\n")
    assert commit_msg.main([str(msg)]) == 1
    msg.write_text("Tweak ignores [ignore-change]\n")
    assert commit_msg.main([str(msg)]) == 0


def test_marker_in_comment_does_not_count():
    assert commit_msg.check([".gitignore"], "Tweak\n# [ignore-change]\n")


def test_other_files_need_no_marker(repo, tmp_path):
    repo.stage("wiki/x.md", "x\n")
    msg = tmp_path / "MSG"
    msg.write_text("Add page\n")
    assert commit_msg.main([str(msg)]) == 0
