"""Deterministic retrieval eligibility and abstention tests."""

from pathlib import Path

import pytest

from app.evaluation.query_intelligence import (
    RetrievalQueryInput,
    RuleBasedRetrievalQueryTransformer,
)
from app.evaluation.retrieval import (
    EvaluationChunk,
    RankedResult,
    evaluate,
    load_dataset,
)
from app.evaluation.retrieval_eligibility import (
    DeterministicRetrievalEligibilityEvaluator,
    EntityState,
    RetrievalEligibilityInput,
    evaluate_eligibility_strategies,
    load_eligibility_dataset,
)

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "app/evaluation/fixtures"
BASE_DATASET = FIXTURES / "retrieval_v1.json"
QUERY_DATASET = FIXTURES / "query_intelligence_v1.json"
ELIGIBILITY_DATASET = FIXTURES / "retrieval_eligibility_v1.json"
BASELINE = ROOT / "app/evaluation/baselines/retrieval_recursive_char_v1.json"


def _result(identity: str, text: str, score: float) -> RankedResult:
    return RankedResult(
        EvaluationChunk(
            chunk_id=identity,
            document_id=f"document-{identity}",
            workspace_id="workspace-a",
            chunk_index=0,
            text=text,
            content_hash=identity,
            chunking_version="recursive-char-v1",
        ),
        score,
    )


def _input(
    query: str,
    *,
    mentioned: tuple[str, ...] = (),
    context: tuple[str, ...] = (),
    results: tuple[RankedResult, ...] = (),
) -> RetrievalEligibilityInput:
    transformed = RuleBasedRetrievalQueryTransformer().transform(
        RetrievalQueryInput(query, "th", context)
    )
    return RetrievalEligibilityInput(
        original_query=query,
        transformation=transformed,
        recent_messages=context,
        original_results=results,
        transformed_results=(results,) if transformed.search_queries else (),
        known_entities=("Basic", "Premium", "PromptPay"),
        mentioned_entities=mentioned,
    )


@pytest.mark.parametrize(
    ("mentioned", "expected"),
    [
        (("Premium",), EntityState.KNOWN),
        (("Diamond",), EntityState.UNKNOWN),
        ((), EntityState.UNSPECIFIED),
    ],
)
def test_entity_assessment(mentioned: tuple[str, ...], expected: EntityState) -> None:
    evaluator = DeterministicRetrievalEligibilityEvaluator()
    assert evaluator.assess_entities(
        mentioned, ("Basic", "Premium")
    ).state is expected


def test_confident_payment_transformation_is_allowed() -> None:
    result = _result("payment", "วิธีการชำระเงิน PromptPay", 0.35)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input("จ่ายยังไง", results=(result,))
    )

    assert "payment methods" in decision.allowed_queries[1]
    assert len(decision.allowed_queries) == 2
    assert decision.eligible is True


def test_objection_without_context_is_gated() -> None:
    result = _result("plans", "Basic Premium ราคา", 0.3)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input("แพงไป", results=(result,))
    )

    assert decision.allowed_queries == ("แพงไป",)
    assert "OBJECTION_TARGET_UNSUPPORTED" in decision.reasons


def test_objection_with_known_context_is_eligible() -> None:
    result = _result("plans", "Basic Premium ราคา", 0.3)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input("แพงไป", context=("Premium ราคาเท่าไหร่",), results=(result,))
    )

    assert len(decision.allowed_queries) == 2
    assert decision.eligible is True


@pytest.mark.parametrize(
    ("query", "entity", "reason"),
    [
        ("Diamond package ราคา", "Diamond", "UNKNOWN_ENTITY"),
        ("จ่ายด้วย Bitcoin", "Bitcoin", "UNKNOWN_ENTITY"),
        ("Premium มีส่วนลด 80%", "Premium", "NO_RELEVANT_KNOWLEDGE"),
        ("Premium รับประกัน 10 ปี", "Premium", "NO_RELEVANT_KNOWLEDGE"),
    ],
)
def test_negative_claims_abstain(query: str, entity: str, reason: str) -> None:
    result = _result("candidate", "Premium ราคา 2,990 รับประกัน Pilot", 0.31)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input(query, mentioned=(entity,), results=(result,))
    )

    assert decision.eligible is False
    assert decision.abstain_reason == reason


def test_agreement_and_confidence_are_bounded() -> None:
    result = _result("plans", "Premium ราคา 2,990", 0.35)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input("Premium ราคาเท่าไหร่", mentioned=("Premium",), results=(result,))
    )

    assert decision.agreement.top_candidate_agreement == 2
    assert decision.agreement.entity_supported is True
    assert 0 <= decision.confidence <= 1


def test_ambiguous_reference_without_context_abstains() -> None:
    result = _result("plans", "Premium ราคา 2,990", 0.3)
    decision = DeterministicRetrievalEligibilityEvaluator().evaluate(
        _input("ตัวนั้นราคาเท่าไหร่", results=(result,))
    )

    assert decision.abstain_reason == "AMBIGUOUS_REFERENCE"


def test_budget_transformation_retrieves_price_vocabulary() -> None:
    transformed = RuleBasedRetrievalQueryTransformer().transform(
        RetrievalQueryInput("มีงบไม่เกิน 3000", "th")
    )

    assert "BUDGET" in transformed.applied_rules
    assert "เปรียบเทียบราคา" in transformed.search_queries[0]
    assert "2,990" not in transformed.search_queries[0]


def test_expanded_dataset_contains_material_negative_set() -> None:
    evaluation = load_eligibility_dataset(
        ELIGIBILITY_DATASET, QUERY_DATASET, BASE_DATASET
    )
    negatives = [case for case in evaluation.dataset.cases if case.negative]
    categories = {case.category for case in negatives}

    assert len(negatives) >= 15
    assert {
        "UNKNOWN_PACKAGE",
        "INVENTED_PROMOTION",
        "IMPOSSIBLE_WARRANTY",
        "UNSUPPORTED_PAYMENT",
        "AMBIGUOUS_REFERENCE",
    } <= categories


def test_strategy_metrics_are_deterministic_safe_and_measure_abstention(
    monkeypatch,
) -> None:
    evaluation = load_eligibility_dataset(
        ELIGIBILITY_DATASET, QUERY_DATASET, BASE_DATASET
    )

    def network_forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("evaluation attempted external network access")

    monkeypatch.setattr("socket.create_connection", network_forbidden)
    first = evaluate_eligibility_strategies(evaluation)
    second = evaluate_eligibility_strategies(evaluation)

    assert first == second
    assert first["external_requests"] == 0
    assert first["negative_cases"] >= 15
    final = first["strategies"]["confidence_abstention"]["metrics"]
    assert final["cross_workspace_leakage_rate"] == 0
    assert final["duplicate_result_ratio"] == 0
    assert 0 <= final["positive_false_abstention_rate"] <= 1
    assert 0 <= final["negative_true_abstention_rate"] <= 1
    assert 0 <= final["unknown_entity_false_positive_rate"] <= 1
    assert first["decision"]["recommendation"] == "IMPLEMENT"
    assert (
        first["decision"]["selected_strategy"]
        == "unknown_entity_claim_topic_gating"
    )
    selected = first["strategies"][first["decision"]["selected_strategy"]]["metrics"]
    original = first["strategies"]["original"]["metrics"]
    assert selected["recall_at_3"] > original["recall_at_3"]
    assert selected["mrr"] > original["mrr"]
    assert selected["negative_query_false_positive_rate"] <= 0.25
    assert selected["unknown_entity_false_positive_rate"] == 0
    assert selected["positive_false_abstention_rate"] <= 0.06


def test_previous_foundation_baseline_remains_reproducible() -> None:
    import json

    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert evaluate(load_dataset(BASE_DATASET)) == expected


def test_production_retrieval_module_is_not_imported() -> None:
    import app.evaluation.retrieval_eligibility as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "app.services.knowledge_retrieval" not in source
    assert "app.knowledge.router" not in source
