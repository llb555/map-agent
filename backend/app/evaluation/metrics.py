"""Dependency-free retrieval and answer metrics used by CI and local runs."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from app.evaluation.models import FactExpectation, RelevantDocument


def rounded(value: float) -> float:
    return round(float(value), 6)


def mean(values: Iterable[float]) -> float:
    rows = list(values)
    return rounded(sum(rows) / len(rows)) if rows else 0.0


def percentile(values: Iterable[float], percent: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    position = (len(rows) - 1) * max(0.0, min(1.0, percent))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return rounded(rows[lower])
    weight = position - lower
    return rounded(rows[lower] * (1 - weight) + rows[upper] * weight)


def normalize_text(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def contains_fact(text: str, fact: str) -> bool:
    normalized_fact = normalize_text(fact)
    return bool(normalized_fact) and normalized_fact in normalize_text(text)


def matches_fact(text: str, fact: FactExpectation) -> bool:
    """Match an accepted expression unless an explicit contradiction is present."""

    if any(contains_fact(text, contradiction) for contradiction in fact.contradictions):
        return False
    return any(contains_fact(text, phrase) for phrase in fact.accepted)


def hit_identity(hit: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(hit.get("chunk_id") or hit.get("document_id") or "").strip(),
        str(hit.get("title") or "").strip(),
        str(hit.get("source_uri") or "").strip(),
    )


def matches_relevant(hit: dict[str, Any], relevant: RelevantDocument) -> bool:
    document_id, title, source_uri = hit_identity(hit)
    # Use the strongest available stable identifier. Title is only a legacy fallback.
    if relevant.document_id:
        return document_id == relevant.document_id
    if relevant.source_uri:
        return source_uri == relevant.source_uri
    return bool(relevant.title and normalize_text(title) == normalize_text(relevant.title))


def relevant_for_hit(hit: dict[str, Any], relevant: tuple[RelevantDocument, ...]) -> RelevantDocument | None:
    matches = [item for item in relevant if matches_relevant(hit, item)]
    return max(matches, key=lambda item: item.relevance) if matches else None


def retrieval_metrics(
    hits: list[dict[str, Any]],
    relevant: tuple[RelevantDocument, ...],
    *,
    cutoffs: tuple[int, ...],
) -> dict[str, float]:
    """Compute binary and graded IR metrics with duplicate hits ignored."""

    metrics: dict[str, float] = {}
    first_relevant_rank: int | None = None
    matched_ids: set[str] = set()
    precisions: list[float] = []
    gains: list[int] = []
    relevant_seen = 0
    for rank, hit in enumerate(hits, start=1):
        match = relevant_for_hit(hit, relevant)
        identity = match.identity() if match else ""
        is_new_match = bool(match and identity not in matched_ids)
        if is_new_match and match is not None:
            matched_ids.add(identity)
            relevant_seen += 1
            gains.append(match.relevance)
            precisions.append(relevant_seen / rank)
            if first_relevant_rank is None:
                first_relevant_rank = rank
        else:
            gains.append(0)

    total_relevant = len({item.identity() for item in relevant})
    depth = max(cutoffs)
    metrics[f"reciprocal_rank@{depth}"] = rounded(1 / first_relevant_rank) if first_relevant_rank else 0.0
    metrics[f"average_precision@{depth}"] = rounded(sum(precisions) / total_relevant) if total_relevant else 0.0

    ideal_gains = sorted((item.relevance for item in relevant), reverse=True)
    for cutoff in cutoffs:
        prefix = hits[:cutoff]
        matched_at_k: set[str] = set()
        gains_at_k: list[int] = []
        for hit in prefix:
            match = relevant_for_hit(hit, relevant)
            identity = match.identity() if match else ""
            if match and identity not in matched_at_k:
                matched_at_k.add(identity)
                gains_at_k.append(match.relevance)
            else:
                gains_at_k.append(0)
        matched_count = len(matched_at_k)
        dcg = sum((2**gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(gains_at_k))
        idcg = sum(
            (2**gain - 1) / math.log2(rank + 2)
            for rank, gain in enumerate(ideal_gains[:cutoff])
        )
        metrics[f"hit_rate@{cutoff}"] = float(matched_count > 0)
        metrics[f"precision@{cutoff}"] = rounded(matched_count / cutoff)
        metrics[f"recall@{cutoff}"] = rounded(matched_count / total_relevant) if total_relevant else 0.0
        metrics[f"ndcg@{cutoff}"] = rounded(dcg / idcg) if idcg else 0.0
    return metrics


def _tokens(text: str) -> list[str]:
    """Tokenize Latin words and CJK characters without external NLP packages."""

    return re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", text.lower())


def token_f1(prediction: str, reference: str) -> float:
    predicted = Counter(_tokens(prediction))
    expected = Counter(_tokens(reference))
    if not predicted or not expected:
        return float(not predicted and not expected)
    common = sum((predicted & expected).values())
    if not common:
        return 0.0
    precision = common / sum(predicted.values())
    recall = common / sum(expected.values())
    return rounded(2 * precision * recall / (precision + recall))


def looks_like_abstention(answer: str) -> bool:
    normalized = normalize_text(answer)
    if not normalized:
        return True
    markers = ("无法回答", "信息不足", "没有足够信息", "不知道", "cannotanswer", "insufficientinformation")
    return any(normalize_text(marker) in normalized for marker in markers)
