"""Optional LLM-as-a-judge scoring for answer quality.

This layer is deliberately opt-in: deterministic metrics remain suitable for CI,
while judge scores help with deeper offline experiments.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.evaluation.metrics import mean
from app.evaluation.models import AnswerPrediction, RAGEvalDataset


class JudgeClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    def chat_completion(self, *, system_prompt: str, user_prompt: str) -> str | None: ...


_SYSTEM_PROMPT = """You are a strict RAG evaluation judge. Score only from the supplied query,
reference answer, expected facts, and retrieved context. Return one JSON object and no markdown:
{"faithfulness": 0.0, "answer_relevance": 0.0, "correctness": 0.0, "reason": "brief reason"}
Each score must be between 0 and 1. Faithfulness means every factual claim is supported by context.
Answer relevance means the response directly answers the query. Correctness means it agrees with
the reference answer and expected facts. Do not reward fluent unsupported claims."""


def _parse_score(raw: str | None) -> dict[str, Any] | None:
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
    scores: dict[str, Any] = {}
    for name in ("faithfulness", "answer_relevance", "correctness"):
        value = payload.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        scores[name] = round(max(0.0, min(1.0, float(value))), 6)
    scores["reason"] = str(payload.get("reason") or "").strip()[:500]
    return scores


def evaluate_with_judge(
    dataset: RAGEvalDataset,
    predictions: dict[str, AnswerPrediction],
    retrieval: dict[str, Any],
    client: JudgeClient,
) -> dict[str, Any]:
    """Evaluate available predictions and preserve failures for auditability."""

    if not client.enabled:
        raise ValueError("llm_judge_api_key_required")
    retrieval_rows = {
        str(row.get("id")): row
        for row in retrieval.get("rows", [])
        if isinstance(row, dict) and row.get("id")
    }
    rows: list[dict[str, Any]] = []
    for case in dataset.cases:
        prediction = predictions.get(case.case_id)
        if prediction is None:
            continue
        retrieved = retrieval_rows.get(case.case_id, {}).get("retrieved", [])
        context = "\n".join(
            f"[{item.get('title')}] {item.get('snippet', '')}"
            for item in retrieved
            if isinstance(item, dict)
        )
        prompt = json.dumps(
            {
                "query": case.query,
                "answer": prediction.answer,
                "reference_answer": case.reference_answer,
                "expected_facts": [list(fact.accepted) for fact in case.required_answer_facts],
                "retrieved_context": context,
            },
            ensure_ascii=False,
        )
        raw = client.chat_completion(system_prompt=_SYSTEM_PROMPT, user_prompt=prompt)
        scores = _parse_score(raw)
        rows.append(
            {
                "id": case.case_id,
                "status": "completed" if scores else "failed",
                "scores": scores or {},
                "raw_response": None if scores else raw,
            }
        )
    completed = [row for row in rows if row["status"] == "completed"]
    return {
        "case_count": len(rows),
        "completed_rate": mean(float(row["status"] == "completed") for row in rows),
        "metrics": {
            name: mean(float(row["scores"][name]) for row in completed)
            for name in ("faithfulness", "answer_relevance", "correctness")
        },
        "rows": rows,
    }
