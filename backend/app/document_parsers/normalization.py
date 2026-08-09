"""Deterministic plain-text normalization."""

import re
import unicodedata

from app.document_parsers.exceptions import (
    ExtractionLimitExceededError,
    NoExtractableTextError,
)

_EXCESSIVE_BLANK_LINES = re.compile(r"\n{4,}")


def normalize_text(text: str, *, maximum_characters: int) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\x00", "")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = _EXCESSIVE_BLANK_LINES.sub("\n\n\n", normalized).strip()
    if not normalized:
        raise NoExtractableTextError("No extractable text")
    if len(normalized) > maximum_characters:
        raise ExtractionLimitExceededError("Extracted text exceeds configured limit")
    return normalized
