"""wiki-init: scaffold a content repository or the restricted vault.

The one tool permitted to write outside the repository it was invoked from,
since its job is to create a new one. The target must be absent, an empty
directory, or (content repo only) the root of an existing git repository such
as a fresh clone; in that last case existing files are never overwritten, only
reported. It never reads the restricted vault: ``--restricted`` only writes
the scaffold.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
from collections.abc import Sequence
from importlib import metadata, resources
from pathlib import Path

from llm_wiki.cli import parser, run
from llm_wiki.config import load_config
from llm_wiki.errors import WikiError
from llm_wiki.paths import RESTRICTED_MARKER, guard_input
from llm_wiki.vault import WIKI_DIRS, catalog_title
from llm_wiki.version import DIST_NAME, pinnable_commit, tools_version

CONTENT_DIRS = (
    "raw/attachments", "raw/docs", "raw/notes", "data", "lint-reports", ".claude/commands",
)
ASSESSMENTS_HEADER = (
    "agency_slug,indicator_id,indicator_version,instrument_version,score,confidence,"
    "assessment_date,pilot,evidence_basis,rationale_page\n"
)
INSTRUMENT_HEADER = "version,released,indicator_versions,change_summary,highest_change_class\n"


def templates() -> Path:
    return Path(str(resources.files("llm_wiki") / "templates"))


def default_tools_url() -> str:
    try:
        urls = metadata.metadata(DIST_NAME).get_all("Project-URL") or []
    except metadata.PackageNotFoundError:
        urls = []
    for entry in urls:
        label, _, url = entry.partition(",")
        if label.strip().lower() == "repository":
            return url.strip()
    raise WikiError("cannot determine the tools repository URL; pass --tools-url")


def render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


class Writer:
    """Writes scaffold files, skipping any that already exist."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.skipped: list[str] = []

    def _claim(self, target: Path) -> bool:
        if target.exists():
            self.skipped.append(str(target.relative_to(self.root)))
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        return True

    def text(self, target: Path, content: str, *, executable: bool = False) -> None:
        if self._claim(target):
            target.write_text(content, encoding="utf-8")
            if executable:
                target.chmod(0o755)

    def copy(self, src: Path, target: Path) -> None:
        if self._claim(target):
            shutil.copyfile(src, target)

    def touch(self, target: Path) -> None:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()


def copy_tree(src: Path, dest: Path, values: dict[str, str], out: Writer) -> None:
    """Copy a template tree, renaming ``dot-x`` to ``.x`` and rendering text files.

    Templates store dotfiles as ``dot-*`` so that, for example, the restricted
    vault's ignore-everything ``.gitignore`` does not apply inside the tools repo.
    """
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if "__pycache__" in rel.parts:
            continue
        rel = Path(*(p.replace("dot-", ".", 1) if p.startswith("dot-") else p for p in rel.parts))
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.suffix in {".md", ".txt", ".yaml", ".csv", ".py"} or path.name.startswith("dot-"):
            out.text(target, render(path.read_text(encoding="utf-8"), values), executable=path.suffix == ".py")
        else:
            out.copy(path, target)


def _prepare_target(target: Path, *, allow_existing_repo: bool) -> bool:
    """Validate the target directory. Returns True when it still needs ``git init``."""
    probe = target if target.exists() else target.parent
    inside = subprocess.run(
        ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    toplevel = Path(inside.stdout.strip()).resolve() if inside.returncode == 0 else None
    if toplevel == target.resolve():
        if not allow_existing_repo:
            raise WikiError(f"{target} is already a git repository; the restricted vault must be created fresh")
        return False
    if target.exists() and any(target.iterdir()):
        raise WikiError(f"{target} exists and is not empty")
    if toplevel is not None:
        raise WikiError(f"{target} is inside the git repository at {toplevel}; choose a location outside it")
    return True


def _git_init(target: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(target)], check=True)


def _codes(values: list[str]) -> str:
    return ", ".join(f"`{v}`" for v in values) or "(none configured)"


def init_content(target: Path, config_path: Path, tools_url: str, tools_rev: str) -> list[str]:
    """Scaffold a content repo. Returns the paths skipped because they already existed."""
    config = load_config(config_path)
    projects = config["projects"]
    today = dt.date.today().isoformat()
    values = {
        "title": config["wiki"]["title"],
        "date": today,
        "tools_url": tools_url,
        "tools_rev": tools_rev,
        "tools_version": tools_version(),
        "project_ids": ", ".join(p["id"] for p in projects),
        "projects_table": "\n".join(
            ["| ID | Project | Kind |", "|----|---------|------|"]
            + [f"| `{p['id']}` | {p['name']} | {p['kind']} |" for p in projects]
        ),
        "project_links": "\n".join(
            f"- [[design/{p['design_dir']}/thesis|{p['id']}: {p['name']}]]" for p in projects
        ),
        "indicator_domains": _codes(config["design"]["indicator_domains"]),
        "module_domains": _codes(config["design"]["module_domains"]),
        "deep_tag": config["tags"]["deep"],
        "skip_tag": config["tags"]["skip"],
    }

    needs_init = _prepare_target(target, allow_existing_repo=True)
    if config_path.resolve() == (target / "wiki.toml").resolve():
        raise WikiError("pass a config file outside the target; wiki-init copies it to wiki.toml")
    target.mkdir(parents=True, exist_ok=True)
    out = Writer(target)
    copy_tree(templates() / "content-repo", target, values, out)
    claude_md = (templates() / "CLAUDE.md.template").read_text(encoding="utf-8")
    out.text(target / "CLAUDE.md", render(claude_md, values))
    out.copy(config_path, target / "wiki.toml")

    for d in CONTENT_DIRS:
        out.touch(target / d / ".gitkeep")
    for d in WIKI_DIRS:
        out.text(
            target / "wiki" / d / "index.md",
            f"# {catalog_title(d)}\n\nCatalog regenerated by `wiki-index`. Do not edit by hand.\n",
        )
    for p in projects:
        design = target / "design" / p["design_dir"]
        out.text(design / "thesis.md", f"# {p['id']}: {p['name']}\n\nThesis to be drafted.\n")
        out.text(design / "open-questions.md", f"# {p['id']}: open questions\n")
    out.text(target / "data" / "assessments.csv", ASSESSMENTS_HEADER)
    out.text(target / "data" / "instrument-versions.csv", INSTRUMENT_HEADER)
    if needs_init:
        _git_init(target)
    return out.skipped


def init_restricted(target: Path) -> None:
    if RESTRICTED_MARKER not in target.name:
        raise WikiError(f"the restricted vault's directory name must contain {RESTRICTED_MARKER!r}, so every tool's path guard recognizes it")
    _prepare_target(target, allow_existing_repo=False)
    target.mkdir(parents=True, exist_ok=True)
    copy_tree(templates() / "restricted-vault", target, {}, Writer(target))
    _git_init(target)


def main(argv: Sequence[str] | None = None) -> int:
    p = parser("wiki-init", "Scaffold a content repository, or the restricted vault with --restricted.")
    p.add_argument("path", type=Path, help="directory to create (must be empty or absent)")
    p.add_argument("--restricted", action="store_true", help="scaffold the restricted vault instead")
    p.add_argument("--config", type=Path, help="a filled-in wiki.toml (content repo only)")
    p.add_argument("--tools-url", help="git URL of the llm-wiki repository (default: package metadata)")
    p.add_argument("--tools-rev", help="full commit SHA to pin (default: the running code's commit, if clean)")
    args = p.parse_args(argv)
    target = args.path.expanduser().resolve()

    if args.restricted:
        init_restricted(target)
        print(f"Restricted vault scaffolded at {target}. It has no remote; never add one.")
        return 0

    if args.config is None:
        raise WikiError("--config is required; copy templates/wiki.toml.template and fill it in")
    config_path = guard_input(args.config)
    tools_rev = args.tools_rev or pinnable_commit()
    if not tools_rev:
        raise WikiError("the running llm-wiki has uncommitted changes, so there is no commit to pin; pass --tools-rev")
    skipped = init_content(target, config_path, args.tools_url or default_tools_url(), tools_rev)
    print(f"Content repository scaffolded at {target}, pinned to llm-wiki {tools_rev[:7]}.")
    for path in skipped:
        print(f"  kept existing {path}; compare it with the template and merge by hand")
    print("Next: create the venv, `pip install -r requirements.txt`, and install the hooks (see README.md).")
    print("The pinned commit must be pushed to the tools remote before pip or pre-commit can fetch it.")
    return 0


def cli() -> int:
    return run(main)
