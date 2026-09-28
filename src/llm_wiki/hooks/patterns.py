"""Text patterns shared by the hooks and lint check 13."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic-key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private-key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
    # Zotero API keys are 24 bare alphanumerics, too generic to match alone.
    "zotero-key": re.compile(
        r"zotero[\w.-]{0,20}(?:key|token|secret)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9]{24}\b",
        re.IGNORECASE,
    ),
}

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")

# North American numbers with separators: (916) 555-0100, 916.555.0100, +1 916 555 0100.
# Bare ten-digit runs are not matched; they collide with identifiers and DOIs.
PHONE = re.compile(r"(?<![\w.])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w])")


def find_secrets(text: str) -> Iterator[tuple[str, str]]:
    for name, pattern in SECRET_PATTERNS.items():
        for m in pattern.finditer(text):
            yield name, _redact(m.group())


def _redact(s: str) -> str:
    return s[:8] + "…" if len(s) > 8 else s


def normalize_email(s: str) -> str:
    return s.strip().lower()


def normalize_phone(s: str) -> str:
    digits = re.sub(r"\D", "", s)
    return digits[-10:]


class Allowlist:
    """Known-public contact details exempt from rule 3 (``leak-allowlist.txt``).

    One entry per line: a full email, a domain wildcard (``@cdt.ca.gov``), or a
    phone number in any format. ``#`` starts a comment.
    """

    def __init__(self, emails: set[str], domains: set[str], phones: set[str]) -> None:
        self.emails, self.domains, self.phones = emails, domains, phones

    @classmethod
    def load(cls, path: Path) -> Allowlist:
        emails: set[str] = set()
        domains: set[str] = set()
        phones: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = line.split("#", 1)[0].strip()
                if not entry:
                    continue
                if entry.startswith("@"):
                    domains.add(entry[1:].lower())
                elif "@" in entry:
                    emails.add(normalize_email(entry))
                else:
                    phones.add(normalize_phone(entry))
        return cls(emails, domains, phones)

    def allows_email(self, email: str) -> bool:
        email = normalize_email(email)
        return email in self.emails or email.rsplit("@", 1)[-1] in self.domains

    def allows_phone(self, phone: str) -> bool:
        return normalize_phone(phone) in self.phones
