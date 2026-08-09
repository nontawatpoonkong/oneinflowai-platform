"""Chunking contracts independent of persistence and embedding providers."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    start_offset: int
    end_offset: int


class ChunkingStrategy(Protocol):
    version: str

    def chunk(self, text: str) -> list[Chunk]: ...
