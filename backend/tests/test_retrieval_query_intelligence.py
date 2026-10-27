"""Deterministic evaluation tests for retrieval query intelligence."""

from pathlib import Path

import pytest

from app.evaluation.query_intelligence import (
    EvaluationStrategy,
    RetrievalQueryInput,
    RuleBasedRetrievalQueryTransformer,
    evaluate_strategies,
    load_query_dataset,
    reciprocal_rank_fusion,
)
from app.evaluation.retrieval import (
    DeterministicEvaluationRetriever,
    EvaluationChunk,
    RankedResult,
    evaluate,
    load_dataset,
)

ROOT = Path(__file__).parents[1]
BASE_DATASET = ROOT / "app/evaluation/fixtures/retrieval_v1.json"
QUERY_DATASET = ROOT / "app/evaluation/fixtures/query_intelligence_v1.json"
BASELINE = ROOT / "app/evaluation/baselines/retrieval_recursive_char_v1.json"


def _transform(message: str, *, context: tuple[str, ...] = ()):
    return RuleBasedRetrievalQueryTransformer().transform(
        RetrievalQueryInput(message, "th", context)
    )


def _result(identity: str, rank_score: float, workspace: str = "workspace-a"):
    chunk = EvaluationChunk(
        chunk_id=identity,
        document_id=f"document-{identity}",
        workspace_id=workspace,
        chunk_index=0,
        text=identity,
        content_hash=identity,
        chunking_version="recursive-char-v1",
    )
    return RankedResult(chunk, rank_score)


@pytest.mark.parametrize(
    ("message", "rule", "term"),
    [
        ("ตัวพรีเมียมกี่บาท", "PRICE", "package price"),
        ("จ่ายยังไง", "PAYMENT", "วิธีการชำระเงิน"),
        ("Premium แพงไปหน่อย", "OBJECTION", "ความคุ้มค่า"),
        ("ตัวไหนต่อไลน์ได้สามอัน", "LINE_FEATURE", "LINE OA"),
        ("What is the current deal?", "PROMOTION", "current promotion"),
    ],
)
def test_transformer_expands_intent_without_business_facts(
    message: str, rule: str, term: str
) -> None:
    transformed = _transform(message)

    assert transformed.original_query == message
    assert rule in transformed.applied_rules
    assert term in transformed.search_queries[0]
    assert "2,990" not in transformed.search_queries[0]
    assert "4,990" not in transformed.search_queries[0]


def test_unmatched_query_preserves_original_without_invented_expansion() -> None:
    transformed = _transform("Diamond lifetime warranty")

    assert transformed.original_query == "Diamond lifetime warranty"
    assert transformed.search_queries == ()
    assert transformed.applied_rules == ()


def test_conversation_aware_composition_is_bounded_and_explicit() -> None:
    transformed = _transform(
        "แล้วตัวไหนถูกกว่า",
        context=("ignored oldest", "Premium ต่างจาก Basic ยังไง"),
    )

    assert transformed.used_conversation_context is True
    assert "Premium ต่างจาก Basic ยังไง" in transformed.search_queries[0]
    assert transformed.original_query == "แล้วตัวไหนถูกกว่า"


def test_rrf_calculation_deduplicates_and_is_deterministic() -> None:
    first = [_result("a", 0.9), _result("b", 0.8)]
    second = [_result("b", 0.95), _result("a", 0.7), _result("c", 0.6)]

    fused = reciprocal_rank_fusion([first, second], rrf_k=60)

    assert [item.chunk.chunk_id for item in fused] == ["b", "a", "c"]
    assert len({item.chunk.chunk_id for item in fused}) == len(fused)
    assert fused == reciprocal_rank_fusion([first, second], rrf_k=60)


def test_rrf_rejects_cross_workspace_input() -> None:
    with pytest.raises(ValueError, match="different workspaces"):
        reciprocal_rank_fusion(
            [[_result("a", 1.0, "workspace-a")], [_result("b", 1.0, "workspace-b")]]
        )


def test_query_dataset_covers_sales_context_and_all_languages() -> None:
    dataset = load_query_dataset(QUERY_DATASET, BASE_DATASET)
    categories = {case.category for case in dataset.cases}
    languages = {case.language for case in dataset.cases}

    assert {"th", "en", "mixed"} <= languages
    assert {
        "PRICE_OBJECTION",
        "BUDGET",
        "FEATURE_REQUIREMENT",
        "COMPARISON",
        "PURCHASE_INTENT",
        "FOLLOW_UP_REFERENCE",
        "PAYMENT",
        "PROMOTION",
    } <= categories
    assert any(case.recent_messages for case in dataset.cases)


def test_strategy_comparison_is_deterministic_isolated_and_offline(monkeypatch) -> None:
    dataset = load_query_dataset(QUERY_DATASET, BASE_DATASET)

    def network_forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("deterministic evaluation attempted network access")

    monkeypatch.setattr("socket.create_connection", network_forbidden)
    first = evaluate_strategies(dataset)
    second = evaluate_strategies(dataset)

    assert first == second
    assert first["external_requests"] == 0
    assert first["decision"]["recommendation"] == "DEFER"
    assert first["decision"]["maximum_negative_false_positive_delta"] > 0
    assert set(first["strategies"]) == {
        strategy.value for strategy in EvaluationStrategy
    }
    for report in first["strategies"].values():
        assert report["metrics"]["cross_workspace_leakage_rate"] == 0.0
        assert report["metrics"]["duplicate_result_ratio"] == 0.0


def test_query_intelligence_does_not_mutate_foundation_baseline() -> None:
    import json

    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert evaluate(load_dataset(BASE_DATASET)) == expected


def test_original_retrieval_component_remains_unchanged() -> None:
    dataset = load_dataset(BASE_DATASET)
    retriever = DeterministicEvaluationRetriever(dataset)
    case = next(case for case in dataset.cases if case.case_id == "th-payment")

    assert retriever.search(case.workspace_id, case.query, limit=5) == []
