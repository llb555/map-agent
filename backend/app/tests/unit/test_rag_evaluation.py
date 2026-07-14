"""Tests for RAG evaluation contracts, metrics, gates, and reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.evaluator import evaluate_answers, evaluate_retrieval
from app.evaluation.gates import evaluate_gates
from app.evaluation.generation import generate_grounded_answers
from app.evaluation.judge import _parse_score, evaluate_with_judge
from app.evaluation.metrics import matches_fact, matches_relevant, retrieval_metrics
from app.evaluation.models import AnswerPrediction, FactExpectation, RelevantDocument, RAGEvalCase, RAGEvalDataset, load_dataset
from app.evaluation.provenance import build_fingerprints, comparison_compatibility, knowledge_manifest
from app.evaluation.reporting import build_markdown_report
from app.core.config import Settings
from app.rag.service import LangChainRAGService


class _FakeSearchService:
    def search(self, *, query: str, top_k: int | None = None) -> dict:
        if "missing" in query:
            return {"status": "completed", "hits": []}
        return {
            "status": "completed",
            "hits": [
                {
                    "chunk_id": "chunk-wrong",
                    "title": "Distractor",
                    "source_uri": "knowledge://wrong",
                    "snippet": "irrelevant",
                    "score": 0.9,
                },
                {
                    "chunk_id": "chunk-right",
                    "title": "Expected",
                    "source_uri": "knowledge://expected",
                    "snippet": "维护状态比较稳定",
                    "score": 0.8,
                },
            ][: top_k or 5],
        }


def _dataset(tmp_path: Path):
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "name": "unit",
                "version": "2.0.0",
                "cases": [
                    {
                        "id": "expected",
                        "query": "maintenance",
                        "tags": ["review"],
                        "relevant_documents": [
                            {"title": "Expected", "source_uri": "knowledge://expected", "relevance": 3}
                        ],
                        "expected_context_facts": ["维护状态比较稳定"],
                        "reference_answer": "机器维护状态比较稳定",
                        "required_answer_facts": ["维护状态比较稳定"],
                        "forbidden_answer_claims": ["从不排队"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return load_dataset(path)


def test_dataset_loader_accepts_legacy_expected_title(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "legacy",
                        "query": "where",
                        "expected_title": "Legacy title",
                        "expected_snippet_substring": "known fact",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    dataset = load_dataset(path)

    assert dataset.cases[0].relevant_documents[0].title == "Legacy title"
    assert dataset.cases[0].expected_context_facts[0].accepted == ("known fact",)


def test_dataset_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "same", "query": "one", "expected_title": "a"},
                    {"id": "same", "query": "two", "expected_title": "b"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate_eval_case_id"):
        load_dataset(path)


def test_retrieval_metrics_support_graded_multi_relevance() -> None:
    relevant = (
        RelevantDocument(title="Primary", relevance=3),
        RelevantDocument(title="Secondary", relevance=1),
    )
    hits = [{"title": "Wrong"}, {"title": "Primary"}, {"title": "Secondary"}]

    metrics = retrieval_metrics(hits, relevant, cutoffs=(1, 3))

    assert metrics["hit_rate@1"] == 0
    assert metrics["hit_rate@3"] == 1
    assert metrics["recall@3"] == 1
    assert metrics["reciprocal_rank@3"] == 0.5
    assert 0 < metrics["ndcg@3"] < 1


def test_retrieval_evaluation_aggregates_slices_and_latency(tmp_path: Path) -> None:
    report = evaluate_retrieval(
        _dataset(tmp_path),
        _FakeSearchService(),
        top_k=3,
        cutoffs=(1, 3),
    )

    assert report["metrics"]["hit_rate@1"] == 0
    assert report["metrics"]["hit_rate@3"] == 1
    assert report["metrics"]["context_fact_recall"] == 1
    assert report["slices"]["review"]["case_count"] == 1
    assert report["latency_ms"]["p95"] >= 0


def test_answer_evaluation_scores_facts_claims_and_citations(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)
    report = evaluate_answers(
        dataset,
        {
            "expected": AnswerPrediction(
                case_id="expected",
                answer="资料显示机器维护状态比较稳定。",
                citations=("knowledge://expected",),
            )
        },
    )

    assert report["metrics"]["required_fact_recall"] == 1
    assert report["metrics"]["forbidden_claim_avoidance"] == 1
    assert report["metrics"]["citation_precision"] == 1
    assert report["metrics"]["citation_recall"] == 1


def test_missing_predictions_do_not_receive_unlabelled_perfect_scores(tmp_path: Path) -> None:
    report = evaluate_answers(_dataset(tmp_path), {})

    assert report["metrics"] == {"prediction_coverage": 0.0}
    assert report["missing_prediction_ids"] == ["expected"]


def test_fact_matching_supports_aliases_and_explicit_contradictions() -> None:
    fact = FactExpectation(
        accepted=("维护状态比较稳定", "维护比较稳定"),
        contradictions=("维护状态不稳定", "并非维护状态比较稳定"),
    )

    assert matches_fact("这里维护比较稳定", fact) is True
    assert matches_fact("并非维护状态比较稳定", fact) is False


def test_relevant_match_uses_stable_uri_before_legacy_title() -> None:
    relevant = RelevantDocument(title="同名文档", source_uri="knowledge://right")

    assert matches_relevant({"title": "同名文档", "source_uri": "knowledge://wrong"}, relevant) is False
    assert matches_relevant({"title": "其他标题", "source_uri": "knowledge://right"}, relevant) is True


def test_no_answer_cases_do_not_pollute_answerable_ir_metrics() -> None:
    dataset = RAGEvalDataset(
        name="no-answer",
        version="1",
        cases=(
            RAGEvalCase(
                case_id="none",
                query="missing",
                relevant_documents=(),
                expected_no_answer=True,
            ),
        ),
    )

    report = evaluate_retrieval(dataset, _FakeSearchService(), top_k=3, cutoffs=(1, 3))

    assert "hit_rate@3" not in report["metrics"]
    assert report["metrics"]["no_answer_retrieval_accuracy"] == 1
    assert report["answerable_case_count"] == 0
    assert report["unanswerable_case_count"] == 1


def test_gate_detects_threshold_and_baseline_regressions() -> None:
    fingerprint = build_fingerprints(
        dataset_sha256="dataset",
        corpus_sha256="corpus",
        top_k=5,
        cutoffs=(1, 5),
        configuration={},
    )
    current = {
        "fingerprints": fingerprint,
        "retrieval": {"metrics": {"hit_rate@5": 0.8}, "latency_ms": {"p95": 20}},
    }
    baseline = {
        "fingerprints": fingerprint,
        "retrieval": {"metrics": {"hit_rate@5": 0.95}},
    }

    result = evaluate_gates(
        current,
        thresholds={
            "minimums": {"retrieval.metrics.hit_rate@5": 0.9},
            "maximums": {"retrieval.latency_ms.p95": 100},
            "regression_metrics": ["retrieval.metrics.hit_rate@5"],
        },
        baseline=baseline,
        max_regression=0.02,
    )

    assert result.passed is False
    assert len(result.failures) == 2


def test_gate_rejects_incompatible_baseline() -> None:
    baseline = {"fingerprints": build_fingerprints(dataset_sha256="a", corpus_sha256="c", top_k=5, cutoffs=(1, 5), configuration={})}
    candidate = {"fingerprints": build_fingerprints(dataset_sha256="b", corpus_sha256="c", top_k=5, cutoffs=(1, 5), configuration={})}

    compatible, differences = comparison_compatibility(baseline, candidate)
    result = evaluate_gates(
        candidate,
        thresholds={"regression_metrics": ["retrieval.metrics.hit_rate@5"]},
        baseline=baseline,
    )

    assert compatible is False
    assert "dataset_sha256" in differences
    assert result.passed is False
    assert result.failures[0].startswith("baseline_incompatible")


def test_knowledge_manifest_excludes_dataset_file(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    document = knowledge / "doc.md"
    dataset = knowledge / "eval.json"
    document.write_text("knowledge", encoding="utf-8")
    dataset.write_text('{"cases": []}', encoding="utf-8")

    manifest = knowledge_manifest(knowledge, excluded_paths={dataset})

    assert manifest["file_count"] == 1
    assert manifest["files"][0]["relative_path"] == "doc.md"


def test_rag_service_does_not_index_the_evaluation_dataset(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    document = knowledge / "doc.md"
    dataset = knowledge / "eval.json"
    document.write_text("维护状态比较稳定", encoding="utf-8")
    dataset.write_text(
        json.dumps(
            {"cases": [{"query": "秘密答案", "expected_title": "doc"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = LangChainRAGService(
        settings=Settings(
            rag_enabled=True,
            rag_source_path=knowledge,
            rag_embedding_model="local-hash-v1",
        ),
        project_root=Path.cwd(),
        excluded_source_paths={dataset},
    )

    service.rebuild_index()

    assert {record.metadata["knowledge_relative_path"] for record in service._chunk_records} == {"doc.md"}


def test_markdown_report_contains_gate_and_core_metrics() -> None:
    markdown = build_markdown_report(
        {
            "run_id": "run-1",
            "dataset": {"name": "demo", "version": "2"},
            "retrieval": {
                "case_count": 1,
                "metrics": {"hit_rate@1": 1.0, "reciprocal_rank": 1.0},
                "latency_ms": {"mean": 1, "p50": 1, "p95": 2},
                "slices": {},
                "failed_case_ids": [],
            },
            "gate": {"passed": True, "failures": []},
        }
    )

    assert "Quality gate: `PASS`" in markdown
    assert "`hit_rate@1`" in markdown


def test_llm_judge_clamps_valid_json_scores(tmp_path: Path) -> None:
    class _FakeJudge:
        enabled = True

        def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
            assert "strict RAG evaluation judge" in system_prompt
            assert "maintenance" in user_prompt
            return json.dumps(
                {
                    "faithfulness": 1.2,
                    "answer_relevance": 0.8,
                    "correctness": -0.1,
                    "reason": "grounded",
                }
            )

    dataset = _dataset(tmp_path)
    result = evaluate_with_judge(
        dataset,
        {
            "expected": AnswerPrediction(
                case_id="expected",
                answer="机器维护状态比较稳定",
                citations=("knowledge://expected",),
            )
        },
        {
            "rows": [
                {
                    "id": "expected",
                    "retrieved": [{"title": "Expected", "snippet": "维护状态比较稳定"}],
                }
            ]
        },
        _FakeJudge(),
    )

    assert result["completed_rate"] == 1
    assert result["metrics"] == {
        "faithfulness": 1.0,
        "answer_relevance": 0.8,
        "correctness": 0.0,
    }


def test_llm_judge_rejects_non_json_response() -> None:
    assert _parse_score("not json") is None


def test_grounded_generation_returns_predictions_and_latency(tmp_path: Path) -> None:
    class _FakeGenerator:
        enabled = True

        def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
            assert "only the supplied retrieved context" in system_prompt
            return json.dumps(
                {"answer": "机器维护状态比较稳定", "citations": ["knowledge://expected"]},
                ensure_ascii=False,
            )

    predictions, report = generate_grounded_answers(
        _dataset(tmp_path),
        {
            "rows": [
                {
                    "id": "expected",
                    "retrieved": [
                        {
                            "title": "Expected",
                            "source_uri": "knowledge://expected",
                            "snippet": "维护状态比较稳定",
                        }
                    ],
                }
            ]
        },
        _FakeGenerator(),
    )

    assert predictions["expected"].citations == ("knowledge://expected",)
    assert report["completed_rate"] == 1
    assert report["latency_ms"]["p95"] >= 0
