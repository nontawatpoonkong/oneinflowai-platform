"""Retrieval-to-prompt orchestration; intentionally performs no generation."""

import time
import uuid

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.rag import RAGContextAssembler, RAGPromptBuilder, RAGPromptPackage
from app.services.knowledge_retrieval import KnowledgeRetrievalService

logger = get_logger(__name__)


class RAGPreparationService:
    def __init__(
        self,
        retrieval: KnowledgeRetrievalService,
        *,
        settings: Settings | None = None,
        assembler: RAGContextAssembler | None = None,
        prompt_builder: RAGPromptBuilder | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retrieval = retrieval
        self.assembler = assembler or RAGContextAssembler(
            max_characters=self.settings.RAG_MAX_CONTEXT_CHARACTERS,
            max_sources=self.settings.RAG_MAX_SOURCES,
        )
        self.prompt_builder = prompt_builder or RAGPromptBuilder()

    async def prepare(
        self,
        *,
        workspace_id: uuid.UUID,
        query: str,
        limit: int | None = None,
        document_id: uuid.UUID | None = None,
    ) -> RAGPromptPackage:
        started = time.perf_counter()
        retrieval = await self.retrieval.search(
            workspace_id=workspace_id,
            query=query,
            limit=limit,
            document_id=document_id,
        )
        context = self.assembler.assemble(retrieval.query, retrieval.results)
        package = self.prompt_builder.build(query=retrieval.query, context=context)
        logger.info(
            "rag_preparation_completed",
            extra={
                "workspace_id": str(workspace_id),
                "retrieved_result_count": len(retrieval.results),
                "included_source_count": context.included_chunk_count,
                "omitted_source_count": context.omitted_chunk_count,
                "context_character_count": context.character_count,
                "context_version": context.version,
                "prompt_version": package.version,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return package
