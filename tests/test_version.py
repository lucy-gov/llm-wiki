import re
import subprocess
import sys

from llm_wiki.version import tools_version, version_string


def test_tools_version_shape():
    assert re.fullmatch(r"[0-9a-f]{7}(-dirty)?|unknown(-dirty)?", tools_version())


def test_dev_checkout_is_dirty():
    # The test suite runs against an editable install or the source tree, both
    # unpinned by construction, so the stamp must say so.
    assert tools_version().endswith("-dirty")


def test_version_flag_on_every_tool():
    for module in ("llm_wiki.cli.init", "llm_wiki.hooks.content", "llm_wiki.hooks.commit_msg", "llm_wiki.hooks.tools_repo"):
        out = subprocess.run(
            [sys.executable, "-c", f"import sys; from {module} import main; sys.argv[0]='x'; main(['--version'])"],
            capture_output=True, text=True,
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == version_string()
