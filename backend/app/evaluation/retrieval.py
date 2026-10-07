"""Deterministic retrieval evaluation runner.

This module is deliberately isolated from runtime retrieval.  Its local hashed
character n-gram vectors make evaluation repeatable for Thai and English while
exercising the production ``recursive-char-v1`` chunker.  They are not a proxy
for the quality of a configured production embedding model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.chunking import RecursiveTextChunker

DATASET_VERSION = "retrieval-eval-v1"
EVALUATOR_VERSION = "hashed-char-ngram-v1"
DEFAULT_DIMENSIONS = 512
DEFAULT_TOP_K = 5
DEFAULT_SCORE_THRESHOLD = 0.12


class EvaluationDataError(ValueError):
    """Raised when a version-controlled evaluation dataset is malformed."""


@dataclass(frozen=True, slots=True)
class EvaluationDocument:
    document_id: str
    workspace_id: str
    language: str
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    language: str
    workspace_id: str
    query: str
    expected_markers: tuple[str, ...]
    category: str
    negative: bool
    notes: str
    recent_messages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    version: str
    documents: tuple[EvaluationDocument, ...]
    cases: tuple[EvaluationCase, ...]


@dataclass(frozen=True, slots=True)
class EvaluationChunk:
    chunk_id: str
    document_id: str
    workspace_id: str
    chunk_index: int
    text: str
    content_hash: str
    chunking_version: str


@dataclass(frozen=True, slots=True)
class RankedResult:
    chunk: EvaluationChunk
    score: float


def _required_string(data: dict[str, Any], field: str, location: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDataError(f"{location}.{field} must be a non-empty string")
    return value


def load_dataset(path: Path) -> EvaluationDataset:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationDataError("evaluation dataset is not valid UTF-8 JSON") from exc
    return parse_dataset(raw)


def parse_dataset(raw: Any) -> EvaluationDataset:
    """Validate an already-decoded evaluation dataset."""
    if not isinstance(raw, dict) or raw.get("version") != DATASET_VERSION:
        raise EvaluationDataError(f"dataset version must be {DATASET_VERSION}")
    raw_workspaces = raw.get("workspaces")
    raw_cases = raw.get("cases")
    if not isinstance(raw_workspaces, list) or not raw_workspaces:
        raise EvaluationDataError("workspaces must be a non-empty list")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EvaluationDataError("cases must be a non-empty list")

    documents: list[EvaluationDocument] = []
    workspace_ids: set[str] = set()
    document_ids: set[str] = set()
    for workspace_index, workspace in enumerate(raw_workspaces):
        if not isinstance(workspace, dict):
            raise EvaluationDataError("workspace entries must be objects")
        location = f"workspaces[{workspace_index}]"
        workspace_id = _required_string(workspace, "workspace_id", location)
        if workspace_id in workspace_ids:
            raise EvaluationDataError(f"duplicate workspace_id: {workspace_id}")
        workspace_ids.add(workspace_id)
        raw_documents = workspace.get("documents")
        if not isinstance(raw_documents, list) or not raw_documents:
            raise EvaluationDataError(f"{location}.documents must be non-empty")
        for document_index, document in enumerate(raw_documents):
            if not isinstance(document, dict):
                raise EvaluationDataError("document entries must be objects")
            document_location = f"{location}.documents[{document_index}]"
            document_id = _required_string(
                document, "document_id", document_location
            )
            if document_id in document_ids:
                raise EvaluationDataError(f"duplicate document_id: {document_id}")
            document_ids.add(document_id)
            documents.append(
                EvaluationDocument(
                    document_id=document_id,
                    workspace_id=workspace_id,
                    language=_required_string(
                        document, "language", document_location
                    ),
                    title=_required_string(document, "title", document_location),
                    content=_required_string(document, "content", document_location),
                )
            )

    cases: list[EvaluationCase] = []
    case_ids: set[str] = set()
    for case_index, case in enumerate(raw_cases):
        if not isinstance(case, dict):
            raise EvaluationDataError("case entries must be objects")
        location = f"cases[{case_index}]"
        case_id = _required_string(case, "case_id", location)
        if case_id in case_ids:
            raise EvaluationDataError(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        workspace_id = _required_string(case, "workspace_id", location)
        if workspace_id not in workspace_ids:
            raise EvaluationDataError(f"unknown workspace_id: {workspace_id}")
        negative = case.get("negative", False)
        if not isinstance(negative, bool):
            raise EvaluationDataError(f"{location}.negative must be boolean")
        markers = case.get("expected_markers", [])
        if not isinstance(markers, list) or any(
            not isinstance(marker, str) or not marker for marker in markers
        ):
            raise EvaluationDataError(
                f"{location}.expected_markers must contain strings"
            )
        if negative and markers:
            raise EvaluationDataError("negative cases cannot have expected markers")
        if not negative and not markers:
            raise EvaluationDataError("positive cases require expected markers")
        for marker in markers:
            if not any(
                marker in document.content
                for document in documents
                if document.workspace_id == workspace_id
            ):
                raise EvaluationDataError(
                    f"expected marker is absent from workspace corpus: {case_id}"
                )
        recent_messages = case.get("recent_messages", [])
        if not isinstance(recent_messages, list) or any(
            not isinstance(message, str) or not message.strip()
            for message in recent_messages
        ):
            raise EvaluationDataError(
                f"{location}.recent_messages must contain non-empty strings"
            )
        cases.append(
            EvaluationCase(
                case_id=case_id,
                language=_required_string(case, "language", location),
                workspace_id=workspace_id,
                query=_required_string(case, "query", location),
                expected_markers=tuple(markers),
                category=_required_string(case, "category", location),
                negative=negative,
                notes=str(case.get("notes", "")),
                recent_messages=tuple(recent_messages),
            )
        )
    return EvaluationDataset(raw["version"], tuple(documents), tuple(cases))


class HashedCharacterNgramEmbedder:
    """Local deterministic multilingual vectorizer used only by the evaluator."""

    name = "evaluation-hashed-char-ngram"
    model = EVALUATOR_VERSION

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        normalized = " ".join(text.casefold().split())
        vector = [0.0] * self.dimensions
        features = Counter()
        padded = f" {normalized} "
        for size in (2, 3, 4):
            features.update(
                padded[index : index + size]
                for index in range(max(0, len(padded) - size + 1))
            )
        for feature, count in features.items():
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * math.log1p(count)
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector


class DeterministicEvaluationRetriever:
    """Workspace-filtered in-memory evaluator with Qdrant-like ranked output."""

    def __init__(
        self,
        dataset: EvaluationDataset,
        *,
        chunk_size: int = 1200,
        overlap: int = 200,
        max_chunks: int = 10_000,
        dimensions: int = DEFAULT_DIMENSIONS,
        score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
    ) -> None:
        self.embedder = HashedCharacterNgramEmbedder(dimensions)
        self.score_threshold = score_threshold
        chunker = RecursiveTextChunker(
            chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks
        )
        chunks: list[EvaluationChunk] = []
        for document in dataset.documents:
            for index, chunk in enumerate(chunker.chunk(document.content)):
                identity = (
                    f"{document.workspace_id}:{document.document_id}:{index}:"
                    f"{chunker.version}"
                )
                chunks.append(
                    EvaluationChunk(
                        chunk_id=hashlib.sha256(identity.encode()).hexdigest()[:32],
                        document_id=document.document_id,
                        workspace_id=document.workspace_id,
                        chunk_index=index,
                        text=chunk.text,
                        content_hash=hashlib.sha256(chunk.text.encode()).hexdigest(),
                        chunking_version=chunker.version,
                    )
                )
        self.chunks = tuple(chunks)
        self.vectors = {
            chunk.chunk_id: self.embedder.embed(chunk.text) for chunk in self.chunks
        }

    def search(
        self, workspace_id: str, query: str, *, limit: int
    ) -> list[RankedResult]:
        query_vector = self.embedder.embed(query)
        ranked = []
        for chunk in self.chunks:
            if chunk.workspace_id != workspace_id:
                continue
            score = sum(
                left * right
                for left, right in zip(
                    query_vector, self.vectors[chunk.chunk_id], strict=True
                )
            )
            if self.score_threshold is None or score >= self.score_threshold:
                ranked.append(RankedResult(chunk, score))
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.chunk.document_id,
                item.chunk.chunk_index,
                item.chunk.chunk_id,
            )
        )
        return ranked[:limit]


def _case_metrics(case: EvaluationCase, results: list[RankedResult], k: int) -> dict:
    selected = results[:k]
    relevant_flags = [
        any(marker in result.chunk.text for marker in case.expected_markers)
        for result in selected
    ]
    covered_markers = {
        marker
        for marker in case.expected_markers
        if any(marker in result.chunk.text for result in selected)
    }
    recall = (
        len(covered_markers) / len(case.expected_markers)
        if case.expected_markers
        else 0.0
    )
    precision = sum(relevant_flags) / k
    return {"recall": recall, "precision": precision, "hit": bool(covered_markers)}


def reciprocal_rank(case: EvaluationCase, results: list[RankedResult]) -> float:
    for rank, result in enumerate(results, start=1):
        if any(marker in result.chunk.text for marker in case.expected_markers):
            return 1.0 / rank
    return 0.0


def duplicate_result_ratio(results: list[RankedResult]) -> float:
    if not results:
        return 0.0
    identities = [result.chunk.chunk_id for result in results]
    return (len(identities) - len(set(identities))) / len(identities)


def evaluate(
    dataset: EvaluationDataset,
    *,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    retriever = DeterministicEvaluationRetriever(
        dataset, score_threshold=score_threshold
    )
    positive_cases = [case for case in dataset.cases if not case.negative]
    negative_cases = [case for case in dataset.cases if case.negative]
    aggregates = {
        k: {"recall": [], "precision": [], "hit": []} for k in (1, 3, 5)
    }
    reciprocal_ranks: list[float] = []
    duplicate_ratios: list[float] = []
    leakage_count = 0
    result_count = 0
    negative_false_positives = 0
    failures: list[dict[str, Any]] = []
    category_hits: dict[str, list[float]] = defaultdict(list)
    language_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()

    for case in dataset.cases:
        language_counts[case.language] += 1
        category_counts[case.category] += 1
        results = retriever.search(case.workspace_id, case.query, limit=max(5, top_k))
        result_count += len(results)
        leakage_count += sum(
            result.chunk.workspace_id != case.workspace_id for result in results
        )
        duplicate_ratios.append(duplicate_result_ratio(results))
        if case.negative:
            if results:
                negative_false_positives += 1
                failures.append(
                    {"case_id": case.case_id, "reason": "NEGATIVE_FALSE_POSITIVE"}
                )
            continue
        rr = reciprocal_rank(case, results)
        reciprocal_ranks.append(rr)
        category_hits[case.category].append(float(rr > 0))
        for k in (1, 3, 5):
            metrics = _case_metrics(case, results, k)
            for name in aggregates[k]:
                aggregates[k][name].append(float(metrics[name]))
        if rr == 0:
            failures.append({"case_id": case.case_id, "reason": "NO_RELEVANT_HIT"})

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    weakest = sorted(
        (
            {"category": category, "hit_rate": mean(values), "cases": len(values)}
            for category, values in category_hits.items()
        ),
        key=lambda item: (item["hit_rate"], item["category"]),
    )
    return {
        "dataset_version": dataset.version,
        "evaluation_mode": "DETERMINISTIC_TEST_MODE",
        "evaluator_version": EVALUATOR_VERSION,
        "embedding_configuration": {
            "provider": "evaluation-hashed-char-ngram",
            "model": EVALUATOR_VERSION,
            "dimensions": DEFAULT_DIMENSIONS,
            "external_requests": 0,
        },
        "chunking_configuration": {
            "version": "recursive-char-v1",
            "target_characters": 1200,
            "overlap_characters": 200,
        },
        "retriever_configuration": {
            "top_k": top_k,
            "score_threshold": score_threshold,
            "distance": "cosine",
            "workspace_filter": True,
        },
        "total_cases": len(dataset.cases),
        "positive_cases": len(positive_cases),
        "negative_cases": len(negative_cases),
        "language_breakdown": dict(sorted(language_counts.items())),
        "category_breakdown": dict(sorted(category_counts.items())),
        "metrics": {
            **{
                f"recall_at_{k}": mean(aggregates[k]["recall"])
                for k in (1, 3, 5)
            },
            **{
                f"precision_at_{k}": mean(aggregates[k]["precision"])
                for k in (1, 3, 5)
            },
            **{
                f"hit_rate_at_{k}": mean(aggregates[k]["hit"])
                for k in (1, 3, 5)
            },
            "mrr": mean(reciprocal_ranks),
            "duplicate_result_ratio": mean(duplicate_ratios),
            "cross_workspace_leakage_rate": (
                round(leakage_count / result_count, 6) if result_count else 0.0
            ),
            "negative_query_false_positive_rate": (
                round(negative_false_positives / len(negative_cases), 6)
                if negative_cases
                else 0.0
            ),
        },
        "failed_cases": failures,
        "weakest_categories": weakest[:5],
    }


def _default_dataset_path() -> Path:
    return Path(__file__).with_name("fixtures") / "retrieval_v1.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=_default_dataset_path())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--score-threshold", type=float, default=DEFAULT_SCORE_THRESHOLD
    )
    args = parser.parse_args()
    report = evaluate(
        load_dataset(args.dataset),
        top_k=args.top_k,
        score_threshold=args.score_threshold,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
