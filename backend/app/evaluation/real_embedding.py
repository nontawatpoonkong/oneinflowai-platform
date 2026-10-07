"""Explicit developer-only real embedding evaluation command.

This module is never imported by application startup or pytest. It embeds only
the version-controlled synthetic corpus and queries in memory; it does not use
PostgreSQL, Qdrant, or production documents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import EmbeddingConfigurationError, EmbeddingProviderError
from app.evaluation.query_intelligence import (
    RetrievalQueryInput,
    RuleBasedRetrievalQueryTransformer,
)
from app.evaluation.retrieval import (
    DeterministicEvaluationRetriever,
    EvaluationDataset,
    RankedResult,
)
from app.evaluation.retrieval_eligibility import (
    EligibilityEvaluationDataset,
    evaluate_eligibility_strategies,
    load_eligibility_dataset,
)
from app.integrations.embedding import create_embedding_provider


class InMemoryRealEmbeddingRetriever:
    """Cosine retriever over synthetic chunks with precomputed provider vectors."""

    def __init__(self, dataset: EvaluationDataset, vectors: dict[str, list[float]]):
        chunk_source = DeterministicEvaluationRetriever(dataset, score_threshold=None)
        self.chunks = chunk_source.chunks
        self.vectors = vectors

    def search(self, workspace_id: str, query: str, *, limit: int):
        query_vector = self.vectors[f"query:{query}"]
        results = []
        for chunk in self.chunks:
            if chunk.workspace_id != workspace_id:
                continue
            chunk_vector = self.vectors[f"chunk:{chunk.chunk_id}"]
            score = sum(
                left * right
                for left, right in zip(query_vector, chunk_vector, strict=True)
            )
            results.append(RankedResult(chunk, score))
        results.sort(
            key=lambda item: (
                -item.score,
                item.chunk.document_id,
                item.chunk.chunk_index,
                item.chunk.chunk_id,
            )
        )
        return results[:limit]


def _texts(evaluation: EligibilityEvaluationDataset):
    chunk_source = DeterministicEvaluationRetriever(
        evaluation.dataset, score_threshold=None
    )
    transformer = RuleBasedRetrievalQueryTransformer()
    items = {f"chunk:{chunk.chunk_id}": chunk.text for chunk in chunk_source.chunks}
    for case in evaluation.dataset.cases:
        transformed = transformer.transform(
            RetrievalQueryInput(case.query, case.language, case.recent_messages)
        )
        for query in (case.query, *transformed.search_queries):
            items[f"query:{query}"] = query
    return items


async def run_real_evaluation(
    evaluation: EligibilityEvaluationDataset, settings: Settings
) -> dict:
    provider = create_embedding_provider(settings)
    items = _texts(evaluation)
    keys = list(items)
    vectors: dict[str, list[float]] = {}
    token_usage = 0
    calls = 0
    model = settings.OPENAI_EMBEDDING_MODEL
    started = time.perf_counter()
    for offset in range(0, len(keys), settings.EMBEDDING_BATCH_SIZE):
        batch_keys = keys[offset : offset + settings.EMBEDDING_BATCH_SIZE]
        result = await provider.embed_texts([items[key] for key in batch_keys])
        calls += 1
        model = result.model
        token_usage += result.token_usage or 0
        for key, vector in zip(batch_keys, result.vectors, strict=True):
            magnitude = math.sqrt(sum(value * value for value in vector))
            vectors[key] = (
                [value / magnitude for value in vector] if magnitude else vector
            )
    retriever = InMemoryRealEmbeddingRetriever(evaluation.dataset, vectors)
    report = evaluate_eligibility_strategies(evaluation, retriever=retriever)
    report["evaluation_mode"] = "REAL_PROVIDER_EVALUATION_MODE"
    report["embedding_configuration"] = {
        "provider": provider.name,
        "model": model,
        "embedding_version": provider.embedding_version,
        "external_requests": calls,
        "embedded_texts": len(items),
        "token_usage": token_usage,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "database_mutations": 0,
        "qdrant_mutations": 0,
    }
    report["external_requests"] = calls
    return report


def _default_path(name: str) -> Path:
    return Path(__file__).with_name("fixtures") / name


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=_default_path("retrieval_eligibility_v1.json")
    )
    parser.add_argument(
        "--query-dataset",
        type=Path,
        default=_default_path("query_intelligence_v1.json"),
    )
    parser.add_argument(
        "--base-dataset", type=Path, default=_default_path("retrieval_v1.json")
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = Settings()
    status = {
        "provider": settings.EMBEDDING_PROVIDER,
        "model": settings.OPENAI_EMBEDDING_MODEL,
        "api_key_configured": bool(settings.OPENAI_API_KEY),
    }
    if settings.EMBEDDING_PROVIDER.strip().lower() == "development":
        print(json.dumps({**status, "error": "REAL_PROVIDER_REQUIRED"}))
        return 2
    try:
        evaluation = load_eligibility_dataset(
            args.dataset, args.query_dataset, args.base_dataset
        )
        report = await run_real_evaluation(evaluation, settings)
    except EmbeddingConfigurationError:
        print(json.dumps({**status, "error": "EMBEDDING_CONFIGURATION_ERROR"}))
        return 2
    except EmbeddingProviderError:
        print(json.dumps({**status, "error": "EMBEDDING_PROVIDER_ERROR"}))
        return 3
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
