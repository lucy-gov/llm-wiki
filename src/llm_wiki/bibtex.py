"""A small BibTeX/BibLaTeX reader for Better BibTeX exports.

Handles ``@string`` macros, ``#`` concatenation, braced and quoted values,
``@comment`` and ``@preamble`` blocks, and text between entries. Field names
are lowercased; values are returned verbatim (braces and LaTeX intact) so that
fields such as ``file`` are never mangled. :func:`latex_to_text` decodes the
fields meant for display.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from llm_wiki.errors import WikiError

MONTHS = {m: str(i) for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1
)}


@dataclass
class Entry:
    type: str
    key: str
    fields: dict[str, str] = field(default_factory=dict)
    line: int = 0


class _Reader:
    def __init__(self, text: str, source: str) -> None:
        self.s = text
        self.i = 0
        self.source = source
        self.macros = dict(MONTHS)

    def error(self, message: str) -> WikiError:
        return WikiError(f"{self.source}:{self.lineno()}: {message}")

    def lineno(self, pos: int | None = None) -> int:
        return self.s.count("\n", 0, self.i if pos is None else pos) + 1

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def expect(self, chars: str) -> str:
        self.ws()
        c = self.peek()
        if not c or c not in chars:
            raise self.error(f"expected {' or '.join(repr(x) for x in chars)}, found {c!r}")
        self.i += 1
        return c

    def ident(self) -> str:
        self.ws()
        m = re.compile(r"[^\s\"#%'(),={}]+").match(self.s, self.i)
        if not m:
            raise self.error("expected a name")
        self.i = m.end()
        return m.group()

    def braced(self) -> str:
        """Contents of a ``{...}`` group; the opening brace is at self.i."""
        depth, start = 0, self.i
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.s[start + 1:self.i - 1]
            self.i += 1
        raise self.error("unbalanced braces")

    def quoted(self) -> str:
        depth, start = 0, self.i
        self.i += 1
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' and depth == 0:
                self.i += 1
                return self.s[start + 1:self.i - 1]
            self.i += 1
        raise self.error("unterminated quoted value")

    def value(self) -> str:
        parts = []
        while True:
            self.ws()
            c = self.peek()
            if c == "{":
                parts.append(self.braced())
            elif c == '"':
                parts.append(self.quoted())
            else:
                name = self.ident()
                parts.append(name if name.isdigit() else self.macros.get(name.lower(), name))
            self.ws()
            if self.peek() != "#":
                return "".join(parts)
            self.i += 1

    def skip_block(self) -> None:
        self.ws()
        if self.peek() == "{":
            self.braced()
        elif self.peek() == "(":
            depth = 0
            while self.i < len(self.s):
                c = self.s[self.i]
                depth += c == "("
                depth -= c == ")"
                self.i += 1
                if depth == 0:
                    return

    def entries(self) -> list[Entry]:
        out: list[Entry] = []
        while True:
            at = self.s.find("@", self.i)
            if at < 0:
                return out
            self.i = at + 1
            kind = self.ident().lower()
            if kind in ("comment", "preamble"):
                self.skip_block()
                continue
            close = "}" if self.expect("{(") == "{" else ")"
            if kind == "string":
                name = self.ident().lower()
                self.expect("=")
                self.macros[name] = self.value()
                self.expect(close)
                continue
            line = self.lineno(at)
            self.ws()
            m = re.compile(r"[^,\s}]*").match(self.s, self.i)
            key = m.group() if m else ""
            self.i = m.end() if m else self.i
            entry = Entry(kind, key, line=line)
            while True:
                sep = self.expect(",}" if close == "}" else ",)")
                if sep == close:
                    break
                self.ws()
                if self.peek() == close:
                    self.i += 1
                    break
                name = self.ident().lower()
                self.expect("=")
                entry.fields[name] = self.value()
            out.append(entry)


def parse(text: str, *, source: str = "<bib>") -> list[Entry]:
    return _Reader(text, source).entries()


# Display decoding

_ACCENTS = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
    "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
    "c": "\u0327", "k": "\u0328", "r": "\u030a", "d": "\u0323", "b": "\u0331",
}
_SYMBOLS = {
    "ss": "ß", "o": "ø", "O": "Ø", "aa": "å", "AA": "Å", "ae": "æ", "AE": "Æ",
    "oe": "œ", "OE": "Œ", "l": "ł", "L": "Ł", "i": "ı", "j": "ȷ",
    "textendash": "–", "textemdash": "—", "textquoteright": "’", "textquoteleft": "‘",
    "textquotedblleft": "“", "textquotedblright": "”", "textellipsis": "…",
    "dots": "…", "ldots": "…", "textsection": "§", "textregistered": "®",
    "texttrademark": "™", "copyright": "©", "textcopyright": "©", "textdegree": "°",
    "euro": "€", "pounds": "£", "S": "§", "P": "¶",
}
_ACCENT_RE = re.compile(r"""\\([`'^"~=.])\s*(?:\{\s*(\\?[A-Za-z])\s*\}|(\\?[A-Za-z]))|\\([uvHckrdb])(?:\s*\{\s*(\\?[A-Za-z])\s*\}|\s+(\\?[A-Za-z]))""")
_SYMBOL_RE = re.compile(r"\\([A-Za-z]+)(?![A-Za-z])(?:\{\})?\s?")
_STYLE_RE = re.compile(r"\\(?:emph|textit|textbf|textsc|textrm|textsf|texttt|mkbibquote|mkbibemph|url|enquote|textsuperscript|textsubscript|mbox)\s*\{")


def _accent(m: re.Match[str]) -> str:
    mark = _ACCENTS[m.group(1) or m.group(4)]
    base = next(g for g in (m.group(2), m.group(3), m.group(5), m.group(6)) if g)
    base = {"\\i": "i", "\\j": "j"}.get(base, base)
    return unicodedata.normalize("NFC", base + mark)


def latex_to_text(value: str) -> str:
    """Best-effort LaTeX → plain Unicode for titles, names, and keywords."""
    s = _STYLE_RE.sub("{", value)
    s = _ACCENT_RE.sub(_accent, s)
    s = _SYMBOL_RE.sub(lambda m: _SYMBOLS.get(m.group(1), m.group(0)), s)
    s = re.sub(r"\\([&%$#_{}~^\\])", lambda m: {"~": "~", "^": "^", "\\": "\\"}.get(m.group(1), m.group(1)), s)
    s = s.replace("---", "—").replace("--", "–").replace("``", "“").replace("''", "”")
    s = re.sub(r"(?<!\\)~", " ", s)
    s = re.sub(r"(?<!\\)[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def split_names(value: str) -> list[str]:
    """Split an author/editor field on top-level ``and``."""
    names, depth, start = [], 0, 0
    for m in re.finditer(r"[{}]|\s+and\s+", value, flags=re.IGNORECASE):
        tok = m.group()
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
        elif depth == 0:
            names.append(value[start:m.start()])
            start = m.end()
    names.append(value[start:])
    return [n for n in (latex_to_text(x) for x in names) if n]


def split_files(value: str) -> list[str]:
    """Attachment paths from a Better BibTeX ``file`` field.

    Paths are separated by unescaped ``;``. The JabRef-style
    ``description:path:mimetype`` form is also accepted.
    """
    parts, buf, i = [], [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            buf.append(value[i + 1])
            i += 2
            continue
        if c == ";":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    out = []
    for p in (x.strip() for x in parts):
        if not p:
            continue
        m = re.fullmatch(r"[^:]*:(.+):[a-z]+/[\w.+-]+", p)
        out.append(m.group(1) if m else p)
    return out
