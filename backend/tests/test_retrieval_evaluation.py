"""Deterministic retrieval evaluation framework tests."""

import json
from pathlib import Path

import pytest

from app.evaluation.retrieval import (
    DATASET_VERSION,
    DeterministicEvaluationRetriever,
    EvaluationCase,
    EvaluationChunk,
    EvaluationDataError,
    RankedResult,
    _case_metrics,
    duplicate_result_ratio,
    evaluate,
    load_dataset,
    reciprocal_rank,
)

ROOT = Path(__file__).parents[1]
DATASET = ROOT / "app/evaluation/fixtures/retrieval_v1.json"
BASELINE = ROOT / "app/evaluation/baselines/retrieval_recursive_char_v1.json"


def _case(*, negative: bool = False) -> EvaluationCase:
    return EvaluationCase(
        case_id="metric-case",
        language="mixed",
        workspace_id="workspace-a",
        query="Premium price",
        expected_markers=() if negative else ("relevant marker",),
        category="PRICE",
        negative=negative,
        notes="",
    )


def _result(identity: str, text: str, score: float = 1.0) -> RankedResult:
    return RankedResult(
        EvaluationChunk(
            chunk_id=identity,
            document_id="document-a",
            workspace_id="workspace-a",
            chunk_index=0,
            text=text,
            content_hash=identity,
            chunking_version="recursive-char-v1",
        ),
        score,
    )


def test_recall_precision_hit_rate_and_mrr() -> None:
    case = _case()
    ranked = [
        _result("irrelevant", "other fact"),
        _result("relevant", "contains relevant marker", 0.8),
    ]
    at_one = _case_metrics(case, ranked, 1)
    at_three = _case_metrics(case, ranked, 3)

    assert at_one == {"recall": 0.0, "precision": 0.0, "hit": False}
    assert at_three == {
        "recall": 1.0,
        "precision": pytest.approx(1 / 3),
        "hit": True,
    }
    assert reciprocal_rank(case, ranked) == 0.5


def test_duplicate_result_ratio_uses_chunk_identity() -> None:
    ranked = [
        _result("same", "first"),
        _result("same", "duplicate"),
        _result("unique", "third"),
    ]
    assert duplicate_result_ratio(ranked) == pytest.approx(1 / 3)
    assert duplicate_result_ratio([]) == 0.0


def test_dataset_parses_all_languages_categories_and_conflicting_workspaces() -> None:
    dataset = load_dataset(DATASET)
    languages = {case.language for case in dataset.cases}
    categories = {case.category for case in dataset.cases}

    assert dataset.version == DATASET_VERSION
    assert languages == {"th", "en", "mixed"}
    assert {"PRICE", "NEGATIVE", "CROSS_WORKSPACE", "NEEDS_DISCOVERY"} <= categories
    assert len({document.workspace_id for document in dataset.documents}) == 3
    assert any("2,990" in document.content for document in dataset.documents)
    assert any("4,990" in document.content for document in dataset.documents)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update(version="unknown"),
        lambda raw: raw["cases"][0].update(expected_markers=[]),
        lambda raw: raw["cases"][0].update(workspace_id="missing"),
        lambda raw: raw["cases"][0].update(case_id=""),
        lambda raw: raw["cases"][0].update(expected_markers=["absent marker"]),
    ],
)
def test_malformed_dataset_is_rejected(tmp_path: Path, mutation) -> None:
    raw = json.loads(DATASET.read_text(encoding="utf-8"))
    mutation(raw)
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(EvaluationDataError):
        load_dataset(path)


def test_workspace_filter_prevents_conflicting_fact_leakage() -> None:
    dataset = load_dataset(DATASET)
    retriever = DeterministicEvaluationRetriever(dataset, score_threshold=None)
    thai = retriever.search("thai-shop", "Premium 4,990", limit=20)
    english = retriever.search("english-shop", "Premium 2,990", limit=20)

    assert thai and english
    assert {result.chunk.workspace_id for result in thai} == {"thai-shop"}
    assert {result.chunk.workspace_id for result in english} == {"english-shop"}


def test_negative_queries_are_measured_separately() -> None:
    report = evaluate(load_dataset(DATASET))
    false_positives = {
        item["case_id"]
        for item in report["failed_cases"]
        if item["reason"] == "NEGATIVE_FALSE_POSITIVE"
    }

    assert report["negative_cases"] == 3
    assert report["metrics"]["negative_query_false_positive_rate"] == pytest.approx(
        len(false_positives) / 3
    )


def test_baseline_is_deterministic_and_contains_no_secrets() -> None:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    first = evaluate(load_dataset(DATASET))
    second = evaluate(load_dataset(DATASET))
    rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)

    assert first == second == expected
    assert first["embedding_configuration"]["external_requests"] == 0
    assert first["metrics"]["cross_workspace_leakage_rate"] == 0.0
    assert "API_KEY" not in rendered
    assert "Authorization" not in rendered


def test_dataset_text_preserves_thai_english_and_mixed_content() -> None:
    dataset = load_dataset(DATASET)
    corpus = "\n".join(document.content for document in dataset.documents)

    assert "ราคา 2,990 บาทต่อเดือน" in corpus
    assert "Premium costs 4,990 THB per month" in corpus
    assert "Hotel Pro ราคา 3,200 THB/month" in corpus
