"""Evidence-based claim/topic eligibility evaluation tests."""

import json
from pathlib import Path

import pytest

from app.evaluation.claim_topic import (
    ClaimState,
    ClaimTopicEligibilityEvaluator,
    ClaimTopicEligibilityInput,
    TopicState,
)
from app.evaluation.retrieval import (
    EvaluationChunk,
    RankedResult,
    evaluate,
    load_dataset,
)
from app.evaluation.retrieval_eligibility import (
    evaluate_eligibility_strategies,
    load_eligibility_dataset,
)

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "app/evaluation/fixtures"
BASE = FIXTURES / "retrieval_v1.json"
QUERY = FIXTURES / "query_intelligence_v1.json"
ELIGIBILITY = FIXTURES / "retrieval_eligibility_v1.json"
BASELINE = ROOT / "app/evaluation/baselines/retrieval_recursive_char_v1.json"


def _candidate(text: str, identity: str = "chunk-a") -> RankedResult:
    return RankedResult(
        EvaluationChunk(
            chunk_id=identity,
            document_id="document-a",
            workspace_id="workspace-a",
            chunk_index=0,
            text=text,
            content_hash=f"hash-{identity}",
            chunking_version="recursive-char-v1",
        ),
        0.4,
    )


def _evaluate(query: str, evidence: str, *, entity_state: str = "KNOWN"):
    return ClaimTopicEligibilityEvaluator().evaluate(
        ClaimTopicEligibilityInput(
            original_query=query,
            transformed_queries=(),
            recent_messages=(),
            recognized_intents=(),
            entity_state=entity_state,
            candidates=(_candidate(evidence),),
        )
    )


@pytest.mark.parametrize(
    ("query", "evidence", "topic", "state"),
    [
        (
            "Premium ราคาเท่าไหร่",
            "Premium ราคา 2,990 บาท",
            "PRICE",
            TopicState.SUPPORTED,
        ),
        (
            "Premium หุ้นน่าลงทุนไหม",
            "Premium ราคา 2,990 บาท",
            "INVESTMENT",
            TopicState.UNSUPPORTED,
        ),
        ("Premium เหมาะไหม", "Premium ราคา 2,990 บาท", None, TopicState.UNKNOWN),
        (
            "Premium รับประกันไหม",
            "การรับประกันบริการ ไม่มี SLA",
            "WARRANTY",
            TopicState.SUPPORTED,
        ),
        ("จ่ายด้วยอะไร", "วิธีการชำระเงิน PromptPay", "PAYMENT", TopicState.SUPPORTED),
        ("รองรับ LINE ไหม", "Premium รองรับ LINE OA", "FEATURE", TopicState.SUPPORTED),
    ],
)
def test_topic_states(
    query: str, evidence: str, topic: str | None, state: TopicState
) -> None:
    result = _evaluate(query, evidence)
    assert result.topic == topic
    assert result.topic_state is state


@pytest.mark.parametrize(
    ("query", "evidence", "state"),
    [
        ("Premium ราคา 2,990", "Premium ราคา 2,990 บาท", ClaimState.SUPPORTED),
        ("Premium ราคา 4,990", "Premium ราคา 2,990 บาท", ClaimState.CONFLICTING),
        ("Premium ลด 80%", "Premium promotion ลด 10%", ClaimState.CONFLICTING),
        (
            "Premium warranty 10 years",
            "Premium warranty information",
            ClaimState.UNSUPPORTED,
        ),
        (
            "Premium โปรซื้อหนึ่งแถมหนึ่ง",
            "Premium promotion ลด 10%",
            ClaimState.UNSUPPORTED,
        ),
    ],
)
def test_numeric_claim_states(query: str, evidence: str, state: ClaimState) -> None:
    assert _evaluate(query, evidence).claim_state is state


@pytest.mark.parametrize(
    ("query", "evidence", "entity_state"),
    [
        ("Premium หุ้นน่าลงทุนไหม", "Premium costs 4,990 THB", "KNOWN"),
        ("Premium support Shopify?", "Premium supports LINE OA", "UNKNOWN"),
        ("Premium จ่าย Bitcoin ได้ไหม", "ชำระด้วย PromptPay", "UNKNOWN"),
        ("Premium รับประกัน 10 ปี", "รับประกันบริการ ไม่มี SLA", "KNOWN"),
    ],
)
def test_unsupported_known_entity_queries_are_ineligible(
    query: str, evidence: str, entity_state: str
) -> None:
    assert _evaluate(query, evidence, entity_state=entity_state).eligible is False


def test_unknown_entity_is_ineligible_even_with_matching_topic() -> None:
    result = _evaluate("Diamond ราคาเท่าไหร่", "ราคาแพ็กเกจ", entity_state="UNKNOWN")
    assert result.eligible is False


def test_evidence_mapping_preserves_chunk_document_and_hash() -> None:
    result = _evaluate("Premium ราคาเท่าไหร่", "Premium ราคา 2,990 บาท")
    assert result.evidence[0].chunk_id == "chunk-a"
    assert result.evidence[0].document_id == "document-a"
    assert result.evidence[0].content_hash == "hash-chunk-a"


def test_combined_strategy_is_deterministic_and_has_no_workspace_leakage(
    monkeypatch,
) -> None:
    evaluation = load_eligibility_dataset(ELIGIBILITY, QUERY, BASE)

    def forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("normal evaluation attempted network access")

    monkeypatch.setattr("socket.create_connection", forbidden)
    first = evaluate_eligibility_strategies(evaluation)
    second = evaluate_eligibility_strategies(evaluation)
    assert first == second
    combined = first["strategies"]["unknown_entity_claim_topic_gating"]
    assert combined["metrics"]["cross_workspace_leakage_rate"] == 0
    assert combined["metrics"]["duplicate_result_ratio"] == 0


def test_budget_objection_and_language_cases_remain_covered() -> None:
    evaluation = load_eligibility_dataset(ELIGIBILITY, QUERY, BASE)
    report = evaluate_eligibility_strategies(evaluation)
    combined = report["strategies"]["unknown_entity_claim_topic_gating"]
    weakest = {item["category"]: item["hit_rate"] for item in combined["weakest"]}
    languages = {case.language for case in evaluation.dataset.cases}
    assert languages == {"th", "en", "mixed"}
    assert weakest.get("BUDGET", 1.0) == 1.0
    assert weakest.get("OBJECTION_CONTEXT", 1.0) == 1.0


def test_previous_baseline_remains_reproducible_and_production_is_untouched() -> None:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert evaluate(load_dataset(BASE)) == expected
    source = (ROOT / "app/evaluation/claim_topic.py").read_text(encoding="utf-8")
    assert "app.services.knowledge_retrieval" not in source
    assert "app.knowledge.router" not in source
