"""wiki-init: scaffold a content repository or the restricted vault.

The one tool permitted to write outside the repository it was invoked from,
since its job is to create a new one. It refuses to write into a non-empty
directory or inside an existing git repository, and it never reads the
restricted vault: ``--restricted`` only writes the scaffold.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import tomllib
from collections.abc import Sequence
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from llm_wiki.cli import parser, run
from llm_wiki.errors import WikiError
from llm_wiki.paths import RESTRICTED_MARKER, guard_input
from llm_wiki.version import DIST_NAME, pinnable_commit, tools_version

WIKI_DIRS = (
    "sources", "agencies", "policies", "jurisdictions", "concepts",
    "methods", "debates", "timelines", "findings", "assessments",
)
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


def copy_tree(src: Path, dest: Path, values: dict[str, str]) -> None:
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
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix in {".md", ".txt", ".yaml", ".csv", ".py"} or path.name.startswith("dot-"):
            target.write_text(render(path.read_text(encoding="utf-8"), values), encoding="utf-8")
        else:
            shutil.copyfile(path, target)
        if path.suffix == ".py":
            target.chmod(0o755)


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WikiError(f"no config at {path}; start from templates/wiki.toml.template") from None
    except tomllib.TOMLDecodeError as exc:
        raise WikiError(f"{path}: {exc}") from None
    projects = config.get("projects") or []
    if not projects:
        raise WikiError(f"{path}: declare at least one [[projects]] table")
    seen = set()
    for i, project in enumerate(projects, start=1):
        for field in ("id", "name", "kind", "design_dir"):
            if not str(project.get(field, "")).strip():
                raise WikiError(f"{path}: project {i} is missing `{field}`")
        pid = project["id"]
        if not pid.replace("-", "").isalnum() or pid.lower() != pid:
            raise WikiError(f"{path}: project id {pid!r} must be lowercase letters, digits, and hyphens")
        if pid in seen:
            raise WikiError(f"{path}: duplicate project id {pid!r}")
        seen.add(pid)
    config.setdefault("wiki", {}).setdefault("title", "Research Wiki")
    config.setdefault("tags", {}).setdefault("deep", "deep")
    config["tags"].setdefault("skip", "skip")
    design = config.setdefault("design", {})
    design.setdefault("indicator_domains", [])
    design.setdefault("module_domains", [])
    return config


def _refuse_unsafe_target(target: Path) -> None:
    if target.exists() and any(target.iterdir()):
        raise WikiError(f"{target} exists and is not empty")
    probe = target if target.exists() else target.parent
    inside = subprocess.run(
        ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if inside.returncode == 0:
        raise WikiError(f"{target} is inside the git repository at {inside.stdout.strip()}; choose a location outside it")


def _git_init(target: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(target)], check=True)


def _codes(values: list[str]) -> str:
    return ", ".join(f"`{v}`" for v in values) or "(none configured)"


def init_content(target: Path, config_path: Path, tools_url: str, tools_rev: str) -> None:
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

    _refuse_unsafe_target(target)
    target.mkdir(parents=True, exist_ok=True)
    copy_tree(templates() / "content-repo", target, values)
    claude_md = (templates() / "CLAUDE.md.template").read_text(encoding="utf-8")
    (target / "CLAUDE.md").write_text(render(claude_md, values), encoding="utf-8")
    shutil.copyfile(config_path, target / "wiki.toml")

    for d in CONTENT_DIRS:
        (target / d).mkdir(parents=True, exist_ok=True)
        (target / d / ".gitkeep").touch()
    for d in WIKI_DIRS:
        (target / "wiki" / d).mkdir(parents=True, exist_ok=True)
        (target / "wiki" / d / "index.md").write_text(
            f"# {d.capitalize()}\n\nCatalog regenerated by `wiki-index`. Do not edit by hand.\n",
            encoding="utf-8",
        )
    for p in projects:
        design = target / "design" / p["design_dir"]
        design.mkdir(parents=True, exist_ok=True)
        (design / "thesis.md").write_text(f"# {p['id']}: {p['name']}\n\nThesis to be drafted.\n", encoding="utf-8")
        (design / "open-questions.md").write_text(f"# {p['id']}: open questions\n", encoding="utf-8")
    (target / "data" / "assessments.csv").write_text(ASSESSMENTS_HEADER, encoding="utf-8")
    (target / "data" / "instrument-versions.csv").write_text(INSTRUMENT_HEADER, encoding="utf-8")
    _git_init(target)


def init_restricted(target: Path) -> None:
    if RESTRICTED_MARKER not in target.name:
        raise WikiError(f"the restricted vault's directory name must contain {RESTRICTED_MARKER!r}, so every tool's path guard recognizes it")
    _refuse_unsafe_target(target)
    target.mkdir(parents=True, exist_ok=True)
    copy_tree(templates() / "restricted-vault", target, {})
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
    init_content(target, config_path, args.tools_url or default_tools_url(), tools_rev)
    print(f"Content repository scaffolded at {target}, pinned to llm-wiki {tools_rev[:7]}.")
    print("Next: create the venv, `pip install -r requirements.txt`, and install the hooks (see README.md).")
    print("The pinned commit must be pushed to the tools remote before pip or pre-commit can fetch it.")
    return 0


def cli() -> int:
    return run(main)
