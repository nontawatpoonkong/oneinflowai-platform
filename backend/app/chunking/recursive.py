"""Deterministic boundary-aware character chunker.

Offsets use ``[start_offset, end_offset)`` and every chunk is an exact source
slice. Grapheme handling is deliberately lightweight: boundaries are moved
away from combining marks, variation selectors, emoji modifiers, and ZWJ
sequences. It does not claim full Unicode grapheme-cluster segmentation.
"""

import re
import unicodedata

from app.chunking.base import Chunk

_SENTENCE_END = re.compile(r"[.!?。！？](?:[\"'”’)]*)\s*")


class RecursiveTextChunker:
    version = "recursive-char-v1"

    def __init__(self, *, chunk_size: int, overlap: int, max_chunks: int) -> None:
        if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("invalid chunk size or overlap")
        if max_chunks <= 0:
            raise ValueError("max_chunks must be greater than zero")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_chunks = max_chunks

    def chunk(self, text: str) -> list[Chunk]:
        if not text:
            raise ValueError("extracted content is empty")
        chunks: list[Chunk] = []
        start = 0
        length = len(text)
        while start < length:
            if len(chunks) >= self.max_chunks:
                raise ValueError("document exceeds maximum chunk count")
            maximum_end = min(start + self.chunk_size, length)
            end = (
                length
                if maximum_end == length
                else self._preferred_end(text, start, maximum_end)
            )
            end = self._safe_end(text, start, end)
            if end <= start:
                end = maximum_end
            chunks.append(
                Chunk(text=text[start:end], start_offset=start, end_offset=end)
            )
            if end == length:
                break
            next_start = max(start + 1, end - self.overlap)
            next_start = self._safe_start(text, next_start, end)
            if next_start >= end:
                next_start = end
            start = next_start
        return chunks

    @staticmethod
    def _preferred_end(text: str, start: int, maximum_end: int) -> int:
        # Reject extremely early boundaries; they produce pathological tiny chunks.
        floor = start + max(1, (maximum_end - start) // 5)
        window = text[floor:maximum_end]
        paragraph = window.rfind("\n\n")
        if paragraph >= 0:
            return floor + paragraph + 2
        newline = window.rfind("\n")
        if newline >= 0:
            return floor + newline + 1
        sentences = list(_SENTENCE_END.finditer(window))
        if sentences:
            return floor + sentences[-1].end()
        for index in range(maximum_end - 1, floor - 1, -1):
            if text[index].isspace():
                return index + 1
        return maximum_end

    @classmethod
    def _safe_end(cls, text: str, start: int, end: int) -> int:
        while end > start and end < len(text) and cls._unsafe_boundary(text, end):
            end -= 1
        return end

    @classmethod
    def _safe_start(cls, text: str, start: int, upper: int) -> int:
        while start > 0 and start < upper and cls._unsafe_boundary(text, start):
            start -= 1
        return start

    @staticmethod
    def _unsafe_boundary(text: str, index: int) -> bool:
        current = text[index]
        previous = text[index - 1]
        codepoint = ord(current)
        return (
            bool(unicodedata.combining(current))
            or current == "\u200d"
            or previous == "\u200d"
            or 0xFE00 <= codepoint <= 0xFE0F
            or 0x1F3FB <= codepoint <= 0x1F3FF
        )


Chunk = Chunk
