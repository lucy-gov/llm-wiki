"""Hashed participant-identifier denylist.

The denylist is written by ``scripts/build-denylist.py`` inside the restricted
vault and read here. Both sides must normalize identically; the restricted-vault
script is a standalone copy (it may not import this package's assumptions about
the main repo), and ``tests/test_denylist.py`` asserts the two agree.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from llm_wiki.hooks.patterns import EMAIL, PHONE, normalize_email, normalize_phone

DEFAULT_PATH = Path("~/.config/llm-wiki/denylist").expanduser()
MAX_NGRAM = 4

_TOKEN = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def normalize_name(s: str) -> str:
    """NFKC, casefold, strip diacritics, keep word tokens, single-space join."""
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", s).casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(_TOKEN.findall(s))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load(path: Path = DEFAULT_PATH) -> frozenset[str] | None:
    """Hashes in the denylist, or None when the file is absent."""
    if not path.exists():
        return None
    hashes = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            hashes.add(line.lower())
    return frozenset(hashes)


def candidates(text: str) -> Iterator[tuple[str, str]]:
    """(hash, human-readable label) for every n-gram, email, and phone in ``text``.

    Labels never include the matched text itself: printing it would put the
    identifier into terminal scrollback and CI logs.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        tokens = normalize_name(line).split()
        for n in range(1, MAX_NGRAM + 1):
            for i in range(len(tokens) - n + 1):
                yield digest(" ".join(tokens[i : i + n])), f"line {lineno}: {n}-word span"
        for m in EMAIL.finditer(line):
            yield digest(normalize_email(m.group())), f"line {lineno}: email"
        for m in PHONE.finditer(line):
            yield digest(normalize_phone(m.group())), f"line {lineno}: phone"


def hits(text: str, hashes: frozenset[str]) -> list[str]:
    return sorted({label for h, label in candidates(text) if h in hashes})
