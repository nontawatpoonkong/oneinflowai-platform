"""Evaluation-only query transformation and multi-query retrieval strategies.

Nothing in this module is imported by the production retrieval path. The rule
transformer expands intent vocabulary, never business facts, and always keeps
the customer's original query available.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.evaluation.retrieval import (
    DEFAULT_SCORE_THRESHOLD,
    DEFAULT_TOP_K,
    DeterministicEvaluationRetriever,
    EvaluationCase,
    EvaluationDataError,
    EvaluationDataset,
    RankedResult,
    _case_metrics,
    duplicate_result_ratio,
    load_dataset,
    parse_dataset,
    reciprocal_rank,
)

QUERY_DATASET_VERSION = "query-intelligence-eval-v1"
TRANSFORMER_VERSION = "rule-query-intelligence-v1"
DEFAULT_RRF_K = 60


@dataclass(frozen=True, slots=True)
class RetrievalQueryInput:
    current_message: str
    language: str
    recent_messages: tuple[str, ...] = ()
    known_entities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QueryTransformation:
    original_query: str
    search_queries: tuple[str, ...]
    transformer: str
    applied_rules: tuple[str, ...]
    used_conversation_context: bool


class RetrievalQueryTransformer(Protocol):
    """Provider-neutral contract for retrieval query understanding."""

    def transform(self, query: RetrievalQueryInput) -> QueryTransformation: ...


class RuleBasedRetrievalQueryTransformer:
    """Small deterministic vocabulary expansion for measured weak intents."""

    _RULES = (
        (
            "BUDGET",
            ("งบ", "budget", "ไม่เกิน", "under "),
            "ราคาแพ็กเกจ เปรียบเทียบราคา package prices price comparison budget",
        ),
        (
            "PAYMENT",
            ("จ่าย", "ชำระ", "พร้อมเพย์", "payment", "pay "),
            "วิธีการชำระเงิน ช่องทางชำระเงิน payment methods payment options",
        ),
        (
            "PRICE",
            ("กี่บาท", "ราคา", "แพง", "ถูกกว่า", "price", "cost", "cheaper"),
            "ราคาแพ็กเกจ package price cost",
        ),
        (
            "OBJECTION",
            ("แพงไป", "คุ้มกว่า", "too expensive", "better value"),
            "เปรียบเทียบแพ็กเกจ ตัวเลือกที่ถูกกว่า ความคุ้มค่า "
            "package comparison cheaper option benefits",
        ),
        (
            "LINE_FEATURE",
            ("ต่อไลน์", "line 3", "line สาม", "line ได้"),
            "รองรับ LINE OA จำนวนบัญชี supports LINE OA accounts",
        ),
        (
            "PROMOTION",
            ("โปรอะไร", "โปรโมชั่น", "promotion", "deal"),
            "โปรโมชั่นปัจจุบัน current promotion offer",
        ),
        (
            "COMPARISON",
            ("ต่างกัน", "ต่างจาก", "ตัวไหน", "which one", "difference"),
            "เปรียบเทียบแพ็กเกจ package comparison differences",
        ),
    )

    def transform(self, query: RetrievalQueryInput) -> QueryTransformation:
        original = " ".join(query.current_message.split())
        if not original:
            raise ValueError("current_message must not be empty")
        context = " ".join(message.strip() for message in query.recent_messages[-4:])
        matching_text = f"{context} {original}".casefold()
        expansions: list[str] = []
        applied: list[str] = []
        for name, triggers, expansion in self._RULES:
            if any(trigger in matching_text for trigger in triggers):
                applied.append(name)
                expansions.append(expansion)
        if query.known_entities:
            applied.append("KNOWN_ENTITIES")
            expansions.append(" ".join(query.known_entities))
        contextual = bool(context and self._is_context_dependent(original))
        prefix = f"บริบทก่อนหน้า previous context: {context}. " if contextual else ""
        transformed = " ".join(
            part for part in (prefix, original, *expansions) if part
        ).strip()
        searches = (transformed,) if transformed != original else ()
        return QueryTransformation(
            original_query=original,
            search_queries=searches,
            transformer=TRANSFORMER_VERSION,
            applied_rules=tuple(applied),
            used_conversation_context=contextual,
        )

    @staticmethod
    def _is_context_dependent(message: str) -> bool:
        folded = message.casefold()
        references = (
            "แล้ว",
            "ตัวไหน",
            "เมื่อกี้",
            "อันนั้น",
            "which one",
            "that one",
            "previous",
        )
        return any(reference in folded for reference in references)


class EvaluationStrategy(StrEnum):
    ORIGINAL = "original"
    TRANSFORMED = "transformed"
    ORIGINAL_TRANSFORMED_RRF = "original_transformed_rrf"
    CONVERSATION_AWARE_RRF = "conversation_aware_rrf"


def reciprocal_rank_fusion(
    rankings: list[list[RankedResult]], *, rrf_k: int = DEFAULT_RRF_K
) -> list[RankedResult]:
    """Fuse workspace-consistent rankings and deduplicate by chunk identity."""
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    workspaces = {
        result.chunk.workspace_id for ranking in rankings for result in ranking
    }
    if len(workspaces) > 1:
        raise ValueError("cannot fuse results from different workspaces")
    fused_scores: dict[str, float] = defaultdict(float)
    best: dict[str, RankedResult] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for rank, result in enumerate(ranking, start=1):
            identity = result.chunk.chunk_id
            if identity in seen:
                continue
            seen.add(identity)
            fused_scores[identity] += 1.0 / (rrf_k + rank)
            current = best.get(identity)
            if current is None or result.score > current.score:
                best[identity] = result
    return [
        RankedResult(best[identity].chunk, fused_scores[identity])
        for identity in sorted(
            best,
            key=lambda item: (
                -fused_scores[item],
                -best[item].score,
                best[item].chunk.document_id,
                best[item].chunk.chunk_index,
                item,
            ),
        )
    ]


def load_query_dataset(path: Path, base_path: Path) -> EvaluationDataset:
    base = load_dataset(base_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationDataError("query dataset is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("version") != QUERY_DATASET_VERSION:
        raise EvaluationDataError(
            f"query dataset version must be {QUERY_DATASET_VERSION}"
        )
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationDataError("query dataset cases must be a non-empty list")
    combined = {
        "version": base.version,
        "workspaces": _dataset_workspaces(base),
        "cases": [_case_json(case) for case in base.cases] + cases,
    }
    return parse_dataset(combined)


def _dataset_workspaces(dataset: EvaluationDataset) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for document in dataset.documents:
        grouped[document.workspace_id].append(
            {
                "document_id": document.document_id,
                "language": document.language,
                "title": document.title,
                "content": document.content,
            }
        )
    return [
        {"workspace_id": workspace, "documents": documents}
        for workspace, documents in sorted(grouped.items())
    ]


def _case_json(case: EvaluationCase) -> dict:
    return {
        "case_id": case.case_id,
        "language": case.language,
        "workspace_id": case.workspace_id,
        "query": case.query,
        "expected_markers": list(case.expected_markers),
        "category": case.category,
        "negative": case.negative,
        "notes": case.notes,
        "recent_messages": list(case.recent_messages),
    }


def retrieve_for_strategy(
    retriever: DeterministicEvaluationRetriever,
    case: EvaluationCase,
    strategy: EvaluationStrategy,
    *,
    transformer: RetrievalQueryTransformer,
    limit: int,
) -> list[RankedResult]:
    transformed = transformer.transform(
        RetrievalQueryInput(
            current_message=case.query,
            language=case.language,
            recent_messages=(
                case.recent_messages
                if strategy is EvaluationStrategy.CONVERSATION_AWARE_RRF
                else ()
            ),
        )
    )
    if strategy is EvaluationStrategy.ORIGINAL:
        queries = (transformed.original_query,)
    elif strategy is EvaluationStrategy.TRANSFORMED:
        queries = transformed.search_queries or (transformed.original_query,)
    elif strategy is EvaluationStrategy.ORIGINAL_TRANSFORMED_RRF:
        queries = (transformed.original_query, *transformed.search_queries)
    else:
        queries = (transformed.original_query, *transformed.search_queries)
    rankings = [
        retriever.search(case.workspace_id, query, limit=limit) for query in queries
    ]
    if len(rankings) == 1:
        return rankings[0]
    return reciprocal_rank_fusion(rankings)[:limit]


def evaluate_strategies(
    dataset: EvaluationDataset,
    *,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
) -> dict:
    retriever = DeterministicEvaluationRetriever(
        dataset, score_threshold=score_threshold
    )
    transformer = RuleBasedRetrievalQueryTransformer()
    reports = {
        strategy.value: _evaluate_strategy(
            dataset, retriever, transformer, strategy, top_k
        )
        for strategy in EvaluationStrategy
    }
    baseline = reports[EvaluationStrategy.ORIGINAL.value]["metrics"]
    for report in reports.values():
        report["delta_vs_original"] = {
            metric: round(value - baseline[metric], 6)
            for metric, value in report["metrics"].items()
        }
    negative_regression = max(
        report["metrics"]["negative_query_false_positive_rate"]
        - baseline["negative_query_false_positive_rate"]
        for report in reports.values()
    )
    return {
        "dataset_version": QUERY_DATASET_VERSION,
        "evaluation_mode": "DETERMINISTIC_TEST_MODE",
        "transformer_version": TRANSFORMER_VERSION,
        "rrf_k": DEFAULT_RRF_K,
        "external_requests": 0,
        "total_cases": len(dataset.cases),
        "strategies": reports,
        "decision": {
            "recommendation": "DEFER",
            "reason": "negative false-positive rate materially worsened",
            "maximum_negative_false_positive_delta": round(
                negative_regression, 6
            ),
        },
    }


def _evaluate_strategy(
    dataset: EvaluationDataset,
    retriever: DeterministicEvaluationRetriever,
    transformer: RetrievalQueryTransformer,
    strategy: EvaluationStrategy,
    top_k: int,
) -> dict:
    negatives = [case for case in dataset.cases if case.negative]
    values = {
        f"{metric}_at_{k}": []
        for metric in ("recall", "precision", "hit_rate")
        for k in (1, 3, 5)
    }
    reciprocal_ranks: list[float] = []
    duplicates: list[float] = []
    leakage = 0
    result_count = 0
    negative_false_positives = 0
    category_hits: dict[str, list[float]] = defaultdict(list)
    failures: list[str] = []
    for case in dataset.cases:
        results = retrieve_for_strategy(
            retriever,
            case,
            strategy,
            transformer=transformer,
            limit=max(5, top_k),
        )
        duplicates.append(duplicate_result_ratio(results))
        leakage += sum(item.chunk.workspace_id != case.workspace_id for item in results)
        result_count += len(results)
        if case.negative:
            negative_false_positives += bool(results)
            continue
        rank = reciprocal_rank(case, results)
        reciprocal_ranks.append(rank)
        category_hits[case.category].append(float(rank > 0))
        if not rank:
            failures.append(case.case_id)
        for k in (1, 3, 5):
            case_metrics = _case_metrics(case, results, k)
            values[f"recall_at_{k}"].append(case_metrics["recall"])
            values[f"precision_at_{k}"].append(case_metrics["precision"])
            values[f"hit_rate_at_{k}"].append(float(case_metrics["hit"]))

    def mean(items: list[float]) -> float:
        return round(sum(items) / len(items), 6) if items else 0.0

    metrics = {name: mean(items) for name, items in values.items()}
    metrics.update(
        {
            "mrr": mean(reciprocal_ranks),
            "duplicate_result_ratio": mean(duplicates),
            "cross_workspace_leakage_rate": (
                round(leakage / result_count, 6) if result_count else 0.0
            ),
            "negative_query_false_positive_rate": (
                round(negative_false_positives / len(negatives), 6)
                if negatives
                else 0.0
            ),
        }
    )
    weakest = sorted(
        (
            {"category": category, "hit_rate": mean(hits), "cases": len(hits)}
            for category, hits in category_hits.items()
        ),
        key=lambda item: (item["hit_rate"], item["category"]),
    )
    return {"metrics": metrics, "failed_cases": failures, "weakest": weakest[:8]}


def _default_query_dataset_path() -> Path:
    return Path(__file__).with_name("fixtures") / "query_intelligence_v1.json"


def _default_base_dataset_path() -> Path:
    return Path(__file__).with_name("fixtures") / "retrieval_v1.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=_default_query_dataset_path())
    parser.add_argument(
        "--base-dataset", type=Path, default=_default_base_dataset_path()
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_strategies(load_query_dataset(args.dataset, args.base_dataset))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
