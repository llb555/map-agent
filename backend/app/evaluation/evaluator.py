"""Evaluation runners for retrieval, tool execution, and answer predictions."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from time import perf_counter
from typing import Any, Protocol

from app.evaluation.metrics import (
    contains_fact,
    looks_like_abstention,
    matches_fact,
    mean,
    percentile,
    relevant_for_hit,
    retrieval_metrics,
    token_f1,
)
from app.evaluation.models import AnswerPrediction, RAGEvalDataset


class SearchService(Protocol):
    def search(self, *, query: str, top_k: int | None = None) -> dict[str, Any]: ...


def _aggregate(rows: list[dict[str, Any]], *, metric_key: str = "metrics") -> dict[str, float]:
    names = sorted(
        {
            name
            for row in rows
            for name, value in dict(row.get(metric_key) or {}).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    )
    return {name: mean(float(row[metric_key][name]) for row in rows if name in row.get(metric_key, {})) for name in names}


def _slice_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for tag in row.get("tags") or []:
            grouped[str(tag)].append(row)
    return {
        tag: {"case_count": len(items), "metrics": _aggregate(items)}
        for tag, items in sorted(grouped.items())
    }


def evaluate_retrieval(
    dataset: RAGEvalDataset,
    service: SearchService,
    *,
    top_k: int,
    cutoffs: tuple[int, ...],
    cold_cache: bool = False,
    latency_runs: int = 1,
    warmup_runs: int = 0,
) -> dict[str, Any]:
    """Run retrieval evaluation and record quality, latency, and failure details."""

    rows: list[dict[str, Any]] = []
    for case in dataset.cases:
        clear_cache = getattr(service, "_clear_query_cache", None)
        for _ in range(max(0, warmup_runs)):
            if cold_cache and callable(clear_cache):
                clear_cache()
            service.search(query=case.query, top_k=top_k)
        samples: list[float] = []
        result: dict[str, Any] = {"status": "failed", "hits": []}
        error: str | None = None
        for _ in range(max(1, latency_runs)):
            if cold_cache and callable(clear_cache):
                clear_cache()
            started = perf_counter()
            try:
                result = service.search(query=case.query, top_k=top_k)
                error = None
            except Exception as exc:  # An evaluator must report a bad case instead of aborting the suite.
                result = {"status": "failed", "hits": []}
                error = f"{type(exc).__name__}: {exc}"
            samples.append((perf_counter() - started) * 1000)
        raw_hits = result.get("hits") if isinstance(result, dict) else []
        hits = [item for item in raw_hits if isinstance(item, dict)] if isinstance(raw_hits, list) else []
        metrics = (
            {}
            if case.expected_no_answer
            else retrieval_metrics(hits, case.relevant_documents, cutoffs=cutoffs)
        )
        context = "\n".join(str(hit.get("snippet") or "") for hit in hits)
        if case.expected_context_facts:
            fact_matches = [matches_fact(context, fact) for fact in case.expected_context_facts]
            metrics["context_fact_recall"] = mean(float(value) for value in fact_matches)
        if case.expected_no_answer:
            metrics["no_answer_retrieval_accuracy"] = float(not hits)
            metrics["no_answer_false_positive_rate"] = float(bool(hits))
        rows.append(
            {
                "id": case.case_id,
                "query": case.query,
                "tags": list(case.tags),
                "status": str(result.get("status") or "unknown"),
                "latency_ms": round(percentile(samples, 0.50), 3),
                "latency_samples_ms": [round(value, 3) for value in samples],
                "cache_hit": bool(result.get("cache_hit", False)),
                "error": error or result.get("reason"),
                "relevant_documents": [item.identity() for item in case.relevant_documents],
                "retrieved": [
                    {
                        "chunk_id": str(hit.get("chunk_id") or ""),
                        "title": str(hit.get("title") or ""),
                        "source_uri": str(hit.get("source_uri") or ""),
                        "score": hit.get("score"),
                        "snippet": str(hit.get("snippet") or ""),
                        "relevant": relevant_for_hit(hit, case.relevant_documents) is not None,
                    }
                    for hit in hits
                ],
                "metrics": metrics,
            }
        )

    latencies = [
        float(value)
        for row in rows
        for value in row.get("latency_samples_ms", [])
    ]
    completed = sum(row["status"] == "completed" for row in rows)
    case_by_id = {case.case_id: case for case in dataset.cases}
    failed_case_ids = []
    for row in rows:
        case = case_by_id[str(row["id"])]
        quality_passed = (
            float(row["metrics"].get("no_answer_retrieval_accuracy", 0)) == 1
            if case.expected_no_answer
            else float(row["metrics"].get(f"hit_rate@{cutoffs[-1]}", 0)) == 1
        )
        if row["status"] != "completed" or not quality_passed:
            failed_case_ids.append(row["id"])
    return {
        "case_count": len(rows),
        "answerable_case_count": sum(not case.expected_no_answer for case in dataset.cases),
        "unanswerable_case_count": sum(case.expected_no_answer for case in dataset.cases),
        "completed_rate": round(completed / len(rows), 6) if rows else 0.0,
        "metrics": _aggregate(rows),
        "latency_ms": {
            "sample_count": len(latencies),
            "runs_per_case": max(1, latency_runs),
            "warmup_runs_per_case": max(0, warmup_runs),
            "cache_mode": "cold-query-cache" if cold_cache else "configured-cache",
            "mean": mean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 6) if latencies else 0.0,
        },
        "slices": _slice_metrics(rows),
        "failed_case_ids": failed_case_ids,
        "rows": rows,
    }


def evaluate_tool_calls(dataset: RAGEvalDataset, registry: Any, *, top_k: int) -> dict[str, Any]:
    """Verify that retrieval also works through the governed tool boundary."""

    async def run_case(index: int, case: Any) -> Any:
        return await registry.execute(
            call_id=f"rag_eval_{index}",
            tool_name="knowledge_search_tool",
            raw_arguments={"query": case.query, "top_k": top_k},
            allowed_tools=["knowledge_search_tool"],
        )

    rows: list[dict[str, Any]] = []
    for index, case in enumerate(dataset.cases, start=1):
        started = perf_counter()
        result = asyncio.run(run_case(index, case))
        latency_ms = (perf_counter() - started) * 1000
        hits = result.output.get("hits") if isinstance(result.output, dict) else []
        hit_count = len(hits) if isinstance(hits, list) else 0
        rows.append(
            {
                "id": case.case_id,
                "status": result.status,
                "hit_count": hit_count,
                "latency_ms": round(latency_ms, 3),
                "attempt_count": result.attempt_count,
                "error": result.error_message,
            }
        )
    return {
        "case_count": len(rows),
        "success_rate": mean(float(row["status"] == "completed") for row in rows),
        "expected_hit_behavior_rate": mean(
            float((row["hit_count"] == 0) if case.expected_no_answer else (row["hit_count"] > 0))
            for row, case in zip(rows, dataset.cases, strict=True)
        ),
        "latency_ms": {
            "mean": mean(row["latency_ms"] for row in rows),
            "p95": percentile((row["latency_ms"] for row in rows), 0.95),
        },
        "rows": rows,
    }


def evaluate_answers(
    dataset: RAGEvalDataset,
    predictions: dict[str, AnswerPrediction],
) -> dict[str, Any]:
    """Score deterministic answer facts, forbidden claims, citations, and abstention."""

    rows: list[dict[str, Any]] = []
    for case in dataset.cases:
        prediction = predictions.get(case.case_id)
        answer = prediction.answer if prediction else ""
        citations = prediction.citations if prediction else ()
        required_matches = [matches_fact(answer, fact) for fact in case.required_answer_facts]
        forbidden_matches = [contains_fact(answer, claim) for claim in case.forbidden_answer_claims]
        relevant_aliases = set().union(*(item.citation_aliases() for item in case.relevant_documents)) if case.relevant_documents else set()
        correct_citations = {citation for citation in citations if citation in relevant_aliases}
        metrics: dict[str, float] = {
            "prediction_coverage": float(prediction is not None),
        }
        if prediction is not None and case.required_answer_facts:
            metrics["required_fact_recall"] = mean(float(value) for value in required_matches)
        if prediction is not None and case.forbidden_answer_claims:
            metrics["forbidden_claim_avoidance"] = float(not any(forbidden_matches))
        if prediction is not None and case.reference_answer:
            metrics["reference_token_f1"] = token_f1(answer, case.reference_answer)
        if prediction is not None and citations:
            metrics["citation_precision"] = round(len(correct_citations) / len(set(citations)), 6)
        elif prediction is not None and relevant_aliases:
            metrics["citation_precision"] = 0.0
        if prediction is not None and relevant_aliases:
            cited_documents = sum(
                bool(set(citations) & item.citation_aliases()) for item in case.relevant_documents
            )
            metrics["citation_recall"] = round(cited_documents / len(case.relevant_documents), 6)
        if prediction is not None and case.expected_no_answer:
            metrics["abstention_accuracy"] = float(looks_like_abstention(answer))
        rows.append(
            {
                "id": case.case_id,
                "tags": list(case.tags),
                "answer": answer,
                "citations": list(citations),
                "missing_required_facts": [
                    fact.label()
                    for fact, matched in zip(case.required_answer_facts, required_matches, strict=True)
                    if not matched
                ],
                "matched_forbidden_claims": [
                    claim
                    for claim, matched in zip(case.forbidden_answer_claims, forbidden_matches, strict=True)
                    if matched
                ],
                "metrics": metrics,
            }
        )
    return {
        "case_count": len(rows),
        "metrics": _aggregate(rows),
        "slices": _slice_metrics(rows),
        "missing_prediction_ids": [case.case_id for case in dataset.cases if case.case_id not in predictions],
        "unknown_prediction_ids": sorted(set(predictions) - {case.case_id for case in dataset.cases}),
        "rows": rows,
    }
