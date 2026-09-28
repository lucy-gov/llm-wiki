"""Text normalization shared by extraction, hashing, and (later) quote verification."""

from __future__ import annotations

import hashlib
import re
import unicodedata

PAGE_BREAK = "\f"


def clean_extracted(text: str) -> str:
    """Tidy extractor output for the text cache without changing its words.

    NFC-normalizes, unifies line endings, and strips trailing whitespace on each
    line. Page breaks (form feeds) are kept so locators remain recoverable.
    """
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip() + "\n"


def body_hash(text: str) -> str:
    """SHA-256 of body text with whitespace collapsed, so reflowing alone never changes it."""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def first_sentence(text: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    m = re.search(r"(?<=[.!?])\s+(?=[A-Z\"“(\[])", text)
    sentence = text[:m.start()] if m else text
    if len(sentence) <= limit:
        return sentence
    cut = sentence[:limit].rsplit(" ", 1)[0].rstrip(",;:—– ")
    return cut + "…"
