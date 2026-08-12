"""Grounded RAG generation with deterministic citation validation."""

import re
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import Settings, get_settings
from app.core.exceptions import GroundingValidationError
from app.core.logging import get_logger
from app.integrations.generation import (
    GenerationProvider,
    GenerationRequest,
    GenerationResult,
    create_generation_provider,
)
from app.rag import RAGContextSource
from app.services.entitlement import AI_REQUESTS, AI_TOKENS, EntitlementService
from app.services.rag_preparation import RAGPreparationService

logger = get_logger(__name__)
_CITATION_PATTERN = re.compile(r"\[S([1-9]\d*)\]")
_THAI_PATTERN = re.compile(r"[\u0E00-\u0E7F]")


class GroundingStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NO_KNOWLEDGE = "NO_KNOWLEDGE"
    MISSING_CITATIONS = "MISSING_CITATIONS"
    INVALID_CITATIONS = "INVALID_CITATIONS"
    GENERATION_FAILED = "GENERATION_FAILED"


@dataclass(frozen=True, slots=True)
class CitationMetadata:
    label: str
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    score: float
    document_name: str


@dataclass(frozen=True, slots=True)
class GenerationUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    query: str
    answer: str
    grounding_status: GroundingStatus
    citations: list[CitationMetadata]
    generation_skipped: bool
    model: str | None
    provider: str | None
    usage: GenerationUsage | None
    prompt_version: str
    context_version: str


def validate_citations(
    answer: str, sources: list[RAGContextSource]
) -> list[CitationMetadata]:
    available = {source.source_label: source for source in sources}
    referenced: list[str] = []
    for match in _CITATION_PATTERN.finditer(answer):
        label = f"S{match.group(1)}"
        if label not in referenced:
            referenced.append(label)
    if not referenced:
        raise GroundingValidationError(
            details={"grounding_status": GroundingStatus.MISSING_CITATIONS}
        )
    invalid = [label for label in referenced if label not in available]
    if invalid:
        raise GroundingValidationError(
            details={"grounding_status": GroundingStatus.INVALID_CITATIONS}
        )
    return [_citation_metadata(available[label]) for label in referenced]


def _citation_metadata(source: RAGContextSource) -> CitationMetadata:
    return CitationMetadata(
        label=source.source_label,
        document_id=source.document_id,
        chunk_id=source.chunk_id,
        chunk_index=source.chunk_index,
        score=source.score,
        document_name=source.original_filename
        or source.document_title
        or "Untitled document",
    )


class GroundedGenerationService:
    def __init__(
        self,
        preparation: RAGPreparationService,
        provider: GenerationProvider | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.preparation = preparation
        self.provider = provider
        self.settings = settings or get_settings()

    async def answer(
        self,
        *,
        workspace_id: uuid.UUID,
        query: str,
        limit: int | None = None,
        document_id: uuid.UUID | None = None,
    ) -> GroundedAnswer:
        started = time.perf_counter()
        session = getattr(self.preparation, "session", None)
        entitlements = EntitlementService(session) if session is not None else None
        if entitlements is not None:
            await entitlements.require(workspace_id, "ai.enabled")
            await entitlements.require_capacity(workspace_id, AI_REQUESTS)
        package = await self.preparation.prepare(
            workspace_id=workspace_id,
            query=query,
            limit=limit,
            document_id=document_id,
        )
        if not package.sources:
            answer = GroundedAnswer(
                query=package.context.query,
                answer=self._no_knowledge_message(package.context.query),
                grounding_status=GroundingStatus.NO_KNOWLEDGE,
                citations=[],
                generation_skipped=True,
                model=None,
                provider=None,
                usage=None,
                prompt_version=package.version,
                context_version=package.context.version,
            )
            self._log(answer, workspace_id, 0, started)
            return answer

        provider = self.provider or create_generation_provider(self.settings)
        result = await provider.generate(
            GenerationRequest(
                system_prompt=package.system_prompt,
                user_prompt=package.user_prompt,
                temperature=self.settings.GENERATION_TEMPERATURE,
                max_output_tokens=self.settings.GENERATION_MAX_OUTPUT_TOKENS,
            )
        )
        citations = validate_citations(result.text, package.sources)
        if entitlements is not None:
            await entitlements.record(
                workspace_id,
                AI_REQUESTS,
                1,
                provider=result.provider,
                model=result.model,
            )
        if entitlements is not None and result.total_tokens is not None:
            await entitlements.record(
                workspace_id,
                AI_TOKENS,
                result.total_tokens,
                provider=result.provider,
                model=result.model,
            )
        if entitlements is not None:
            await session.commit()
        answer = GroundedAnswer(
            query=package.context.query,
            answer=result.text,
            grounding_status=GroundingStatus.VERIFIED,
            citations=citations,
            generation_skipped=False,
            model=result.model,
            provider=result.provider,
            usage=self._usage(result),
            prompt_version=package.version,
            context_version=package.context.version,
        )
        self._log(answer, workspace_id, len(package.sources), started)
        return answer

    @staticmethod
    def _no_knowledge_message(query: str) -> str:
        if _THAI_PATTERN.search(query):
            return "ไม่พบข้อมูลเพียงพอในฐานความรู้สำหรับตอบคำถามนี้"
        return (
            "There is not enough information in the knowledge base "
            "to answer this question."
        )

    @staticmethod
    def _usage(result: GenerationResult) -> GenerationUsage | None:
        values = (result.input_tokens, result.output_tokens, result.total_tokens)
        if all(value is None for value in values):
            return None
        return GenerationUsage(*values)

    @staticmethod
    def _log(
        answer: GroundedAnswer,
        workspace_id: uuid.UUID,
        source_count: int,
        started: float,
    ) -> None:
        logger.info(
            "grounded_generation_completed",
            extra={
                "workspace_id": str(workspace_id),
                "source_count": source_count,
                "grounding_status": answer.grounding_status,
                "provider": answer.provider,
                "model": answer.model,
                "input_tokens": answer.usage.input_tokens if answer.usage else None,
                "output_tokens": answer.usage.output_tokens if answer.usage else None,
                "generation_skipped": answer.generation_skipped,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
