"""Console-script entry points, one module per tool."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from llm_wiki.errors import WikiError
from llm_wiki.version import version_string


def parser(prog: str, description: str) -> argparse.ArgumentParser:
    """An ArgumentParser carrying the --version flag every tool must expose."""
    p = argparse.ArgumentParser(prog=prog, description=description)
    p.add_argument("--version", action="version", version=version_string())
    return p


def run(main: Callable[[Sequence[str] | None], int], argv: Sequence[str] | None = None) -> int:
    """Call ``main``, turning WikiError into a readable message and exit code 1."""
    try:
        return main(argv)
    except WikiError as exc:
        prog = sys.argv[0].rsplit("/", 1)[-1] if sys.argv else "llm-wiki"
        print(f"{prog}: error: {exc}", file=sys.stderr)
        return 1
