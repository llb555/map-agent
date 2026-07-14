"""Optional grounded answer generation for end-to-end RAG evaluation."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Protocol

from app.evaluation.models import AnswerPrediction, RAGEvalDataset
from app.evaluation.metrics import mean, percentile


class CompletionClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str | None: ...


_SYSTEM_PROMPT = """Answer the query using only the supplied retrieved context. Return one JSON
object and no markdown: {"answer":"...","citations":["source_uri"]}. Cite only source_uri values
present in the context. If the context is insufficient, say that the information is insufficient
and return an empty citations list. Do not invent facts."""


def _parse_prediction(case_id: str, raw: str | None) -> AnswerPrediction | None:
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").removeprefix("json").strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    answer = str(payload.get("answer") or "").strip()
    raw_citations = payload.get("citations")
    citations = (
        tuple(str(item).strip() for item in raw_citations if str(item).strip())
        if isinstance(raw_citations, list)
        else ()
    )
    return AnswerPrediction(case_id=case_id, answer=answer, citations=citations)


def generate_grounded_answers(
    dataset: RAGEvalDataset,
    retrieval: dict[str, Any],
    client: CompletionClient,
) -> tuple[dict[str, AnswerPrediction], dict[str, Any]]:
    """Generate answers from the exact retrieved contexts stored in the report."""

    if not client.enabled:
        raise ValueError("answer_generator_api_key_required")
    retrieval_rows = {
        str(row.get("id")): row
        for row in retrieval.get("rows", [])
        if isinstance(row, dict) and row.get("id")
    }
    predictions: dict[str, AnswerPrediction] = {}
    rows: list[dict[str, Any]] = []
    for case in dataset.cases:
        hits = retrieval_rows.get(case.case_id, {}).get("retrieved", [])
        context = [
            {
                "title": str(hit.get("title") or ""),
                "source_uri": str(hit.get("source_uri") or ""),
                "snippet": str(hit.get("snippet") or ""),
            }
            for hit in hits
            if isinstance(hit, dict)
        ]
        prompt = json.dumps({"query": case.query, "context": context}, ensure_ascii=False)
        started = perf_counter()
        raw = client.chat_completion(system_prompt=_SYSTEM_PROMPT, user_prompt=prompt)
        latency_ms = (perf_counter() - started) * 1000
        prediction = _parse_prediction(case.case_id, raw)
        if prediction is not None:
            predictions[case.case_id] = prediction
        rows.append(
            {
                "id": case.case_id,
                "status": "completed" if prediction is not None else "failed",
                "latency_ms": round(latency_ms, 3),
                "error": None if prediction is not None else "invalid_or_empty_generation",
            }
        )
    latencies = [float(row["latency_ms"]) for row in rows]
    return predictions, {
        "case_count": len(rows),
        "completed_rate": mean(float(row["status"] == "completed") for row in rows),
        "latency_ms": {
            "mean": mean(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "rows": rows,
    }
