"""Deterministic bounded formatting of retrieved knowledge as untrusted data."""

import json
import uuid
from dataclasses import dataclass

from app.services.knowledge_retrieval import RetrievalResult

RAG_CONTEXT_VERSION = "rag-context-v1"


@dataclass(frozen=True, slots=True)
class RAGContextSource:
    source_number: int
    source_label: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    text: str
    score: float
    content_hash: str
    document_title: str | None
    original_filename: str | None


@dataclass(frozen=True, slots=True)
class RAGContext:
    query: str
    sources: list[RAGContextSource]
    formatted_context: str
    included_chunk_count: int
    omitted_chunk_count: int
    character_count: int
    version: str = RAG_CONTEXT_VERSION


class RAGContextAssembler:
    def __init__(self, *, max_characters: int, max_sources: int) -> None:
        if max_characters <= 0 or max_sources <= 0:
            raise ValueError("RAG context limits must be positive")
        self.max_characters = max_characters
        self.max_sources = max_sources

    def assemble(self, query: str, results: list[RetrievalResult]) -> RAGContext:
        seen: set[uuid.UUID] = set()
        sources: list[RAGContextSource] = []
        blocks: list[str] = []
        character_count = 0
        for result in results:
            if result.chunk_id in seen:
                continue
            seen.add(result.chunk_id)
            if len(sources) >= self.max_sources:
                continue
            source_number = len(sources) + 1
            source = RAGContextSource(
                source_number=source_number,
                source_label=f"S{source_number}",
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                chunk_index=result.chunk_index,
                text=result.text,
                score=result.score,
                content_hash=result.content_hash,
                document_title=result.document_title,
                original_filename=result.original_filename,
            )
            block = self._format_source(source)
            separator_size = 2 if blocks else 0
            if character_count + separator_size + len(block) > self.max_characters:
                continue
            sources.append(source)
            blocks.append(block)
            character_count += separator_size + len(block)
        formatted = "\n\n".join(blocks)
        return RAGContext(
            query=query,
            sources=sources,
            formatted_context=formatted,
            included_chunk_count=len(sources),
            omitted_chunk_count=len(results) - len(sources),
            character_count=len(formatted),
        )

    @staticmethod
    def _format_source(source: RAGContextSource) -> str:
        payload = json.dumps(
            {
                "source_label": source.source_label,
                "document": source.original_filename
                or source.document_title
                or "Untitled document",
                "chunk_index": source.chunk_index,
                "content": source.text,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        # Prevent source content from creating look-alike structural tags.
        payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
        return (
            f'<UNTRUSTED_KNOWLEDGE_SOURCE id="{source.source_label}">\n'
            f"{payload}\n"
            f'</UNTRUSTED_KNOWLEDGE_SOURCE id="{source.source_label}">'
        )
