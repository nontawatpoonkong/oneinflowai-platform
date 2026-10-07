"""Deterministic retrieval eligibility and abstention evaluation.

This module is evaluation-only. It does not alter production query,
retrieval, Qdrant, trust revalidation, or RAG behavior.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.evaluation.claim_topic import (
    ClaimTopicEligibilityEvaluator,
    ClaimTopicEligibilityInput,
)
from app.evaluation.query_intelligence import (
    EvaluationStrategy,
    QueryTransformation,
    RetrievalQueryInput,
    RuleBasedRetrievalQueryTransformer,
    load_query_dataset,
    reciprocal_rank_fusion,
    retrieve_for_strategy,
)
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
    parse_dataset,
    reciprocal_rank,
)

ELIGIBILITY_DATASET_VERSION = "retrieval-eligibility-eval-v1"
ELIGIBILITY_EVALUATOR_VERSION = "deterministic-eligibility-v1"
MAXIMUM_NEGATIVE_FALSE_POSITIVE_RATE = 0.25
MAXIMUM_POSITIVE_FALSE_ABSTENTION_RATE = 0.06


class EntityState(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNSPECIFIED = "UNSPECIFIED"


class EligibilityStrategy(StrEnum):
    ORIGINAL = "original"
    CONVERSATION_RRF = "conversation_aware_rrf"
    TRANSFORMATION_ELIGIBILITY = "transformation_eligibility"
    UNKNOWN_ENTITY_GATING = "unknown_entity_gating"
    CLAIM_TOPIC_GATING = "unknown_entity_claim_topic_gating"
    CONFIDENCE_ABSTENTION = "confidence_abstention"


@dataclass(frozen=True, slots=True)
class EntityAssessment:
    state: EntityState
    known: tuple[str, ...]
    unknown: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgreementSignals:
    top_score: float
    score_margin: float
    top_candidate_agreement: int
    entity_supported: bool
    numeric_claim_supported: bool


@dataclass(frozen=True, slots=True)
class RetrievalEligibilityInput:
    original_query: str
    transformation: QueryTransformation
    recent_messages: tuple[str, ...]
    original_results: tuple[RankedResult, ...]
    transformed_results: tuple[tuple[RankedResult, ...], ...]
    known_entities: tuple[str, ...]
    mentioned_entities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalEligibilityDecision:
    eligible: bool
    confidence: float
    reasons: tuple[str, ...]
    allowed_queries: tuple[str, ...]
    abstain_reason: str | None
    entity_assessment: EntityAssessment
    agreement: AgreementSignals


class RetrievalEligibilityEvaluator(Protocol):
    def evaluate(
        self, value: RetrievalEligibilityInput
    ) -> RetrievalEligibilityDecision: ...


class DeterministicRetrievalEligibilityEvaluator:
    """Bounded rules based on entities, context, scores, and rank agreement."""

    _AMBIGUOUS_REFERENCES = (
        "ตัวนั้น",
        "อันนั้น",
        "เมื่อกี้",
        "that one",
        "previous one",
    )

    def assess_entities(
        self, mentioned: tuple[str, ...], known_entities: tuple[str, ...]
    ) -> EntityAssessment:
        known_folded = {entity.casefold(): entity for entity in known_entities}
        known: list[str] = []
        unknown: list[str] = []
        for entity in mentioned:
            canonical = known_folded.get(entity.casefold())
            (known if canonical else unknown).append(canonical or entity)
        state = (
            EntityState.UNKNOWN
            if unknown
            else EntityState.KNOWN
            if known
            else EntityState.UNSPECIFIED
        )
        return EntityAssessment(state, tuple(known), tuple(unknown))

    def evaluate(
        self, value: RetrievalEligibilityInput
    ) -> RetrievalEligibilityDecision:
        entities = self.assess_entities(
            value.mentioned_entities, value.known_entities
        )
        rankings = [value.original_results, *value.transformed_results]
        agreement = self._agreement(value, rankings, entities)
        ambiguous = any(
            marker in value.original_query.casefold()
            for marker in self._AMBIGUOUS_REFERENCES
        ) and not value.recent_messages
        objection = "OBJECTION" in value.transformation.applied_rules
        reasons: list[str] = []
        allowed = [value.transformation.original_query]
        transformation_allowed = bool(value.transformation.applied_rules)
        if objection and entities.state is EntityState.UNSPECIFIED:
            context_text = " ".join(value.recent_messages).casefold()
            if not any(
                entity.casefold() in context_text for entity in value.known_entities
            ):
                transformation_allowed = False
                reasons.append("OBJECTION_TARGET_UNSUPPORTED")
        if entities.state is EntityState.UNKNOWN:
            transformation_allowed = False
            reasons.append("UNKNOWN_ENTITY")
        if ambiguous:
            transformation_allowed = False
            reasons.append("AMBIGUOUS_REFERENCE")
        if transformation_allowed:
            allowed.extend(value.transformation.search_queries)
            reasons.append("RECOGNIZED_INTENT")
        if entities.state is EntityState.KNOWN:
            reasons.append("KNOWN_ENTITY")
        if agreement.top_candidate_agreement >= 2:
            reasons.append("MULTI_QUERY_AGREEMENT")

        confidence = 0.0
        confidence += min(agreement.top_score, 0.4)
        confidence += min(agreement.score_margin, 0.15)
        confidence += 0.2 if agreement.top_candidate_agreement >= 2 else 0.0
        confidence += 0.15 if agreement.entity_supported else 0.0
        confidence += 0.1 if agreement.numeric_claim_supported else 0.0
        confidence = round(min(confidence, 1.0), 6)
        abstain_reason = None
        if entities.state is EntityState.UNKNOWN:
            abstain_reason = "UNKNOWN_ENTITY"
        elif ambiguous:
            abstain_reason = "AMBIGUOUS_REFERENCE"
        elif not any(rankings) or not agreement.numeric_claim_supported:
            abstain_reason = "NO_RELEVANT_KNOWLEDGE"
        elif agreement.top_candidate_agreement < 2 and agreement.top_score < 0.2:
            abstain_reason = "LOW_RETRIEVAL_CONFIDENCE"
        return RetrievalEligibilityDecision(
            eligible=abstain_reason is None,
            confidence=confidence,
            reasons=tuple(reasons),
            allowed_queries=tuple(dict.fromkeys(allowed)),
            abstain_reason=abstain_reason,
            entity_assessment=entities,
            agreement=agreement,
        )

    @staticmethod
    def _agreement(
        value: RetrievalEligibilityInput,
        rankings: list[tuple[RankedResult, ...]],
        entities: EntityAssessment,
    ) -> AgreementSignals:
        non_empty = [ranking for ranking in rankings if ranking]
        top_results = [ranking[0] for ranking in non_empty]
        counts: dict[str, int] = defaultdict(int)
        for result in top_results:
            counts[result.chunk.chunk_id] += 1
        top_agreement = max(counts.values(), default=0)
        best = max(top_results, key=lambda result: result.score, default=None)
        top_score = best.score if best else 0.0
        all_results = sorted(
            (result for ranking in non_empty for result in ranking),
            key=lambda result: -result.score,
        )
        second_score = all_results[1].score if len(all_results) > 1 else 0.0
        margin = max(0.0, top_score - second_score)
        candidate_text = " ".join(
            result.chunk.text for result in top_results
        ).casefold()
        entity_supported = not entities.known or all(
            entity.casefold() in candidate_text for entity in entities.known
        )
        numeric_claims = re.findall(r"\d[\d,.]*%?", value.original_query)
        numeric_supported = not numeric_claims or all(
            claim in candidate_text for claim in numeric_claims
        )
        return AgreementSignals(
            round(top_score, 6),
            round(margin, 6),
            top_agreement,
            entity_supported,
            numeric_supported,
        )


@dataclass(frozen=True, slots=True)
class EligibilityEvaluationDataset:
    dataset: EvaluationDataset
    entity_catalogs: dict[str, tuple[str, ...]]
    mentioned_entities: dict[str, tuple[str, ...]]


def load_eligibility_dataset(
    path: Path, query_path: Path, base_path: Path
) -> EligibilityEvaluationDataset:
    query_dataset = load_query_dataset(query_path, base_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationDataError(
            "eligibility dataset is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict) or raw.get("version") != ELIGIBILITY_DATASET_VERSION:
        raise EvaluationDataError(
            f"eligibility dataset version must be {ELIGIBILITY_DATASET_VERSION}"
        )
    catalogs = raw.get("entity_catalogs")
    cases = raw.get("cases")
    metadata = raw.get("case_metadata", {})
    if not isinstance(catalogs, dict) or not isinstance(cases, list):
        raise EvaluationDataError("eligibility catalogs/cases are malformed")
    workspaces = _dataset_workspaces(query_dataset)
    combined = {
        "version": query_dataset.version,
        "workspaces": workspaces,
        "cases": [_case_json(case) for case in query_dataset.cases] + cases,
    }
    dataset = parse_dataset(combined)
    parsed_catalogs: dict[str, tuple[str, ...]] = {}
    workspace_ids = {document.workspace_id for document in dataset.documents}
    for workspace_id, entities in catalogs.items():
        if workspace_id not in workspace_ids:
            raise EvaluationDataError(
                f"unknown entity catalog workspace: {workspace_id}"
            )
        if not isinstance(entities, list) or any(
            not isinstance(entity, str) or not entity.strip() for entity in entities
        ):
            raise EvaluationDataError("entity catalogs must contain strings")
        parsed_catalogs[workspace_id] = tuple(entities)
    mentioned: dict[str, tuple[str, ...]] = {}
    for case_id, value in metadata.items():
        mentioned[case_id] = _mentioned(value, case_id)
    for case in cases:
        mentioned[case["case_id"]] = _mentioned(case, case["case_id"])
    return EligibilityEvaluationDataset(dataset, parsed_catalogs, mentioned)


def _mentioned(value: dict, case_id: str) -> tuple[str, ...]:
    entities = value.get("mentioned_entities", [])
    if not isinstance(entities, list) or any(
        not isinstance(entity, str) or not entity.strip() for entity in entities
    ):
        raise EvaluationDataError(f"invalid mentioned_entities: {case_id}")
    return tuple(entities)


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


def evaluate_eligibility_strategies(
    evaluation: EligibilityEvaluationDataset,
    *,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float | None = DEFAULT_SCORE_THRESHOLD,
    retriever: object | None = None,
) -> dict:
    dataset = evaluation.dataset
    active_retriever = retriever or DeterministicEvaluationRetriever(
        dataset, score_threshold=score_threshold
    )
    transformer = RuleBasedRetrievalQueryTransformer()
    evaluator = DeterministicRetrievalEligibilityEvaluator()
    reports = {
        strategy.value: _evaluate_strategy(
            evaluation, active_retriever, transformer, evaluator, strategy, top_k
        )
        for strategy in EligibilityStrategy
    }
    baseline = reports[EligibilityStrategy.ORIGINAL.value]["metrics"]
    for report in reports.values():
        report["delta_vs_original"] = {
            name: round(value - baseline[name], 6)
            for name, value in report["metrics"].items()
        }
    candidates = (
        EligibilityStrategy.CLAIM_TOPIC_GATING,
        EligibilityStrategy.UNKNOWN_ENTITY_GATING,
        EligibilityStrategy.CONFIDENCE_ABSTENTION,
    )
    passing = [
        strategy
        for strategy in candidates
        if _passes_decision_gate(reports[strategy.value], baseline)
    ]
    selected = passing[0].value if passing else None
    return {
        "dataset_version": ELIGIBILITY_DATASET_VERSION,
        "evaluation_mode": "DETERMINISTIC_TEST_MODE",
        "evaluator_version": ELIGIBILITY_EVALUATOR_VERSION,
        "external_requests": 0,
        "total_cases": len(dataset.cases),
        "positive_cases": sum(not case.negative for case in dataset.cases),
        "negative_cases": sum(case.negative for case in dataset.cases),
        "strategies": reports,
        "decision": {
            "recommendation": "IMPLEMENT" if selected else "DEFER",
            "selected_strategy": selected,
            "production_change_applied": False,
            "negative_false_positive_gate": MAXIMUM_NEGATIVE_FALSE_POSITIVE_RATE,
        },
    }


def _passes_decision_gate(report: dict, baseline: dict) -> bool:
    metrics = report["metrics"]
    category_hits = {
        item["category"]: item["hit_rate"] for item in report["weakest"]
    }
    required_categories = ("OBJECTION_CONTEXT", "FAQ", "PARAPHRASE", "BUDGET")
    return (
        metrics["recall_at_3"] > baseline["recall_at_3"] + 0.05
        and metrics["mrr"] > baseline["mrr"] + 0.05
        and metrics["negative_query_false_positive_rate"]
        <= MAXIMUM_NEGATIVE_FALSE_POSITIVE_RATE
        and metrics["unknown_entity_false_positive_rate"] == 0
        and metrics["positive_false_abstention_rate"]
        <= MAXIMUM_POSITIVE_FALSE_ABSTENTION_RATE
        and metrics["cross_workspace_leakage_rate"] == 0
        and all(
            category_hits.get(category, 1.0) >= 1.0
            for category in required_categories
        )
    )


def _evaluate_strategy(
    evaluation: EligibilityEvaluationDataset,
    retriever: DeterministicEvaluationRetriever,
    transformer: RuleBasedRetrievalQueryTransformer,
    evaluator: DeterministicRetrievalEligibilityEvaluator,
    strategy: EligibilityStrategy,
    top_k: int,
) -> dict:
    cases = evaluation.dataset.cases
    positives = [case for case in cases if not case.negative]
    negatives = [case for case in cases if case.negative]
    metrics = {
        f"{name}_at_{k}": []
        for name in ("recall", "precision", "hit_rate")
        for k in (1, 3, 5)
    }
    reciprocal_ranks: list[float] = []
    duplicates: list[float] = []
    abstained_positive = 0
    abstained_negative = 0
    unknown_negative = 0
    unknown_false_positive = 0
    leakage = 0
    result_count = 0
    negative_false_positive = 0
    eligible_positive_recalls: list[float] = []
    known_positive_recalls: list[float] = []
    failures: list[str] = []
    false_positive_cases: list[str] = []
    abstained_cases: list[str] = []
    category_hits: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        results, abstained, entity_state = _case_results(
            evaluation, retriever, transformer, evaluator, strategy, case, top_k
        )
        duplicates.append(duplicate_result_ratio(results))
        leakage += sum(
            result.chunk.workspace_id != case.workspace_id for result in results
        )
        result_count += len(results)
        if case.negative:
            negative_false_positive += bool(results)
            abstained_negative += abstained
            if results:
                false_positive_cases.append(case.case_id)
            if abstained:
                abstained_cases.append(case.case_id)
            if entity_state is EntityState.UNKNOWN:
                unknown_negative += 1
                unknown_false_positive += bool(results)
            continue
        abstained_positive += abstained
        if abstained:
            abstained_cases.append(case.case_id)
        rank = reciprocal_rank(case, results)
        reciprocal_ranks.append(rank)
        category_hits[case.category].append(float(rank > 0))
        if not rank:
            failures.append(case.case_id)
        for k in (1, 3, 5):
            case_metric = _case_metrics(case, results, k)
            metrics[f"recall_at_{k}"].append(case_metric["recall"])
            metrics[f"precision_at_{k}"].append(case_metric["precision"])
            metrics[f"hit_rate_at_{k}"].append(float(case_metric["hit"]))
        if not abstained:
            eligible_positive_recalls.append(_case_metrics(case, results, 3)["recall"])
        if entity_state is EntityState.KNOWN:
            known_positive_recalls.append(_case_metrics(case, results, 3)["recall"])

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    calculated = {name: mean(values) for name, values in metrics.items()}
    calculated.update(
        {
            "mrr": mean(reciprocal_ranks),
            "duplicate_result_ratio": mean(duplicates),
            "cross_workspace_leakage_rate": (
                round(leakage / result_count, 6) if result_count else 0.0
            ),
            "negative_query_false_positive_rate": round(
                negative_false_positive / len(negatives), 6
            ),
            "abstention_rate": round(
                (abstained_positive + abstained_negative) / len(cases), 6
            ),
            "negative_true_abstention_rate": round(
                abstained_negative / len(negatives), 6
            ),
            "positive_false_abstention_rate": round(
                abstained_positive / len(positives), 6
            ),
            "eligible_query_recall_at_3": mean(eligible_positive_recalls),
            "unknown_entity_false_positive_rate": (
                round(unknown_false_positive / unknown_negative, 6)
                if unknown_negative
                else 0.0
            ),
            "known_entity_recall_at_3": mean(known_positive_recalls),
        }
    )
    weakest = sorted(
        (
            {"category": category, "hit_rate": mean(hits), "cases": len(hits)}
            for category, hits in category_hits.items()
        ),
        key=lambda item: (item["hit_rate"], item["category"]),
    )
    return {
        "metrics": calculated,
        "failed_cases": failures,
        "negative_false_positive_cases": false_positive_cases,
        "abstained_cases": abstained_cases,
        "weakest": weakest[:8],
    }


def _case_results(
    evaluation: EligibilityEvaluationDataset,
    retriever: DeterministicEvaluationRetriever,
    transformer: RuleBasedRetrievalQueryTransformer,
    evaluator: DeterministicRetrievalEligibilityEvaluator,
    strategy: EligibilityStrategy,
    case: EvaluationCase,
    top_k: int,
) -> tuple[list[RankedResult], bool, EntityState]:
    limit = max(5, top_k)
    query_input = RetrievalQueryInput(
        case.query, case.language, case.recent_messages
    )
    transformed = transformer.transform(query_input)
    original = retriever.search(case.workspace_id, case.query, limit=limit)
    transformed_rankings = [
        retriever.search(case.workspace_id, query, limit=limit)
        for query in transformed.search_queries
    ]
    catalog = evaluation.entity_catalogs[case.workspace_id]
    query_context = " ".join((case.query, *case.recent_messages)).casefold()
    mentioned = evaluation.mentioned_entities.get(case.case_id)
    if mentioned is None:
        mentioned = tuple(
            entity for entity in catalog if entity.casefold() in query_context
        )
    decision = evaluator.evaluate(
        RetrievalEligibilityInput(
            original_query=case.query,
            transformation=transformed,
            recent_messages=case.recent_messages,
            original_results=tuple(original),
            transformed_results=tuple(tuple(items) for items in transformed_rankings),
            known_entities=catalog,
            mentioned_entities=mentioned,
        )
    )
    if strategy is EligibilityStrategy.ORIGINAL:
        return original, False, decision.entity_assessment.state
    if strategy is EligibilityStrategy.CONVERSATION_RRF:
        results = retrieve_for_strategy(
            retriever,
            case,
            EvaluationStrategy.CONVERSATION_AWARE_RRF,
            transformer=transformer,
            limit=limit,
        )
        return results, False, decision.entity_assessment.state
    allowed_transformed = (
        transformed_rankings if len(decision.allowed_queries) > 1 else []
    )
    fused = reciprocal_rank_fusion([original, *allowed_transformed])[:limit]
    if strategy is EligibilityStrategy.TRANSFORMATION_ELIGIBILITY:
        return fused, False, decision.entity_assessment.state
    if (
        strategy is EligibilityStrategy.UNKNOWN_ENTITY_GATING
        and decision.entity_assessment.state is EntityState.UNKNOWN
    ):
        return [], True, decision.entity_assessment.state
    if strategy is EligibilityStrategy.UNKNOWN_ENTITY_GATING:
        return fused, False, decision.entity_assessment.state
    if strategy is EligibilityStrategy.CLAIM_TOPIC_GATING:
        if decision.entity_assessment.state is EntityState.UNKNOWN or (
            "AMBIGUOUS_REFERENCE" in decision.reasons
        ):
            return [], True, decision.entity_assessment.state
        claim_decision = ClaimTopicEligibilityEvaluator().evaluate(
            ClaimTopicEligibilityInput(
                original_query=case.query,
                transformed_queries=transformed.search_queries,
                recent_messages=case.recent_messages,
                recognized_intents=transformed.applied_rules,
                entity_state=decision.entity_assessment.state.value,
                candidates=tuple(fused),
            )
        )
        if not claim_decision.eligible:
            return [], True, decision.entity_assessment.state
        return fused, False, decision.entity_assessment.state
    if not decision.eligible:
        return [], True, decision.entity_assessment.state
    return fused, False, decision.entity_assessment.state


def _default_path(name: str) -> Path:
    return Path(__file__).with_name("fixtures") / name


def main() -> None:
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
    report = evaluate_eligibility_strategies(
        load_eligibility_dataset(args.dataset, args.query_dataset, args.base_dataset)
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
