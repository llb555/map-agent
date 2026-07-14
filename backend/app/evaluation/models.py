"""Dataset and prediction contracts for deterministic RAG evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RelevantDocument:
    """A document or chunk that is relevant to one evaluation query."""

    document_id: str | None = None
    title: str | None = None
    source_uri: str | None = None
    relevance: int = 1

    def identity(self) -> str:
        return self.document_id or self.source_uri or self.title or "unknown"

    def citation_aliases(self) -> frozenset[str]:
        """Return every explicit identifier accepted in generated citations."""

        return frozenset(value for value in (self.document_id, self.source_uri, self.title) if value)


@dataclass(frozen=True)
class FactExpectation:
    """A fact represented by accepted phrases and explicit contradictory phrases."""

    accepted: tuple[str, ...]
    contradictions: tuple[str, ...] = ()

    def label(self) -> str:
        return self.accepted[0] if self.accepted else "unknown"


@dataclass(frozen=True)
class RAGEvalCase:
    """One query with retrieval and optional answer-quality labels."""

    case_id: str
    query: str
    relevant_documents: tuple[RelevantDocument, ...]
    tags: tuple[str, ...] = ()
    expected_context_facts: tuple[FactExpectation, ...] = ()
    reference_answer: str | None = None
    required_answer_facts: tuple[FactExpectation, ...] = ()
    forbidden_answer_claims: tuple[str, ...] = ()
    expected_no_answer: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RAGEvalDataset:
    """A versioned collection of RAG evaluation cases."""

    name: str
    version: str
    cases: tuple[RAGEvalCase, ...]
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerPrediction:
    """An answer and the source identities it claims to cite."""

    case_id: str
    answer: str
    citations: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _facts(value: object) -> tuple[FactExpectation, ...]:
    """Load phrase groups while preserving the original list-of-strings format."""

    if not isinstance(value, list):
        return ()
    facts: list[FactExpectation] = []
    for raw in value:
        if isinstance(raw, str) and raw.strip():
            facts.append(FactExpectation(accepted=(raw.strip(),)))
            continue
        if not isinstance(raw, dict):
            continue
        accepted = _strings(raw.get("accepted"))
        legacy_value = str(raw.get("value") or "").strip()
        if legacy_value and not accepted:
            accepted = (legacy_value,)
        if not accepted:
            continue
        facts.append(
            FactExpectation(
                accepted=accepted,
                contradictions=_strings(raw.get("contradictions")),
            )
        )
    return tuple(facts)


def _relevant_documents(item: dict[str, Any]) -> tuple[RelevantDocument, ...]:
    raw_documents = item.get("relevant_documents")
    documents: list[RelevantDocument] = []
    if isinstance(raw_documents, list):
        for raw in raw_documents:
            if isinstance(raw, str) and raw.strip():
                documents.append(RelevantDocument(title=raw.strip()))
                continue
            if not isinstance(raw, dict):
                continue
            document_id = str(raw.get("document_id") or raw.get("chunk_id") or "").strip() or None
            title = str(raw.get("title") or "").strip() or None
            source_uri = str(raw.get("source_uri") or "").strip() or None
            if not any((document_id, title, source_uri)):
                continue
            relevance = max(1, int(raw.get("relevance") or raw.get("grade") or 1))
            documents.append(
                RelevantDocument(
                    document_id=document_id,
                    title=title,
                    source_uri=source_uri,
                    relevance=relevance,
                )
            )

    # Version 1 datasets used one expected title per case.
    if not documents:
        expected_title = str(item.get("expected_title") or "").strip()
        if expected_title:
            documents.append(RelevantDocument(title=expected_title))
    return tuple(documents)


def load_dataset(path: Path) -> RAGEvalDataset:
    """Load the version 2 contract while accepting the original flat format."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_cases = payload
        root: dict[str, Any] = {}
    elif isinstance(payload, dict):
        root = payload
        raw_cases = payload.get("cases", [])
    else:
        raise ValueError(f"invalid_eval_dataset:{path}")
    if not isinstance(raw_cases, list):
        raise ValueError(f"invalid_eval_cases:{path}")

    cases: list[RAGEvalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            continue
        query = str(raw.get("query") or "").strip()
        case_id = str(raw.get("id") or raw.get("case_id") or f"case_{index}").strip()
        if not query:
            raise ValueError(f"eval_query_required:{case_id}")
        if case_id in seen_ids:
            raise ValueError(f"duplicate_eval_case_id:{case_id}")
        seen_ids.add(case_id)
        relevant = _relevant_documents(raw)
        expected_no_answer = bool(raw.get("expected_no_answer", False))
        if not relevant and not expected_no_answer:
            raise ValueError(f"relevant_documents_required:{case_id}")

        context_facts = _facts(raw.get("expected_context_facts"))
        legacy_snippet = str(raw.get("expected_snippet_substring") or "").strip()
        if legacy_snippet and all(legacy_snippet not in fact.accepted for fact in context_facts):
            context_facts = (*context_facts, FactExpectation(accepted=(legacy_snippet,)))
        cases.append(
            RAGEvalCase(
                case_id=case_id,
                query=query,
                relevant_documents=relevant,
                tags=_strings(raw.get("tags")),
                expected_context_facts=context_facts,
                reference_answer=str(raw.get("reference_answer") or "").strip() or None,
                required_answer_facts=_facts(raw.get("required_answer_facts")),
                forbidden_answer_claims=_strings(raw.get("forbidden_answer_claims")),
                expected_no_answer=expected_no_answer,
                metadata=dict(raw.get("metadata")) if isinstance(raw.get("metadata"), dict) else {},
            )
        )
    if not cases:
        raise ValueError(f"empty_eval_cases:{path}")
    return RAGEvalDataset(
        name=str(root.get("name") or path.stem),
        version=str(root.get("version") or "1"),
        description=str(root.get("description") or ""),
        cases=tuple(cases),
        metadata=dict(root.get("metadata")) if isinstance(root.get("metadata"), dict) else {},
    )


def load_predictions(path: Path) -> dict[str, AnswerPrediction]:
    """Load answer predictions from a list, ``cases`` or ``predictions`` object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("predictions", payload.get("cases", []))
    else:
        raise ValueError(f"invalid_prediction_file:{path}")
    if not isinstance(rows, list):
        raise ValueError(f"invalid_predictions:{path}")

    predictions: dict[str, AnswerPrediction] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("id") or row.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("prediction_case_id_required")
        if case_id in predictions:
            raise ValueError(f"duplicate_prediction_case_id:{case_id}")
        predictions[case_id] = AnswerPrediction(
            case_id=case_id,
            answer=str(row.get("answer") or "").strip(),
            citations=_strings(row.get("citations")),
            metadata=dict(row.get("metadata")) if isinstance(row.get("metadata"), dict) else {},
        )
    return predictions
