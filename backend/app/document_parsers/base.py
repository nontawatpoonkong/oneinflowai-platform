"""Provider-neutral document parsing contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExtractionOutput:
    text: str
    character_count: int
    word_count: int
    method: str
    version: str = "1"


class DocumentParser(ABC):
    mime_types: frozenset[str]

    def supports(self, mime_type: str) -> bool:
        return mime_type.lower() in self.mime_types

    @abstractmethod
    def extract(self, data: bytes) -> str:
        """Extract unnormalized text from trusted, validated document bytes."""
        raise NotImplementedError
