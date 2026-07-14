"""Reproducibility metadata and compatibility checks for RAG experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".pdf", ".docx", ".doc"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_hash(payload: object) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(rendered.encode("utf-8"))


def knowledge_manifest(source_path: Path, *, excluded_paths: set[Path] | None = None) -> dict[str, Any]:
    """Hash supported knowledge files without embedding their private contents."""

    resolved = source_path.resolve()
    excluded = {path.resolve() for path in (excluded_paths or set())}
    if not resolved.exists():
        return {"exists": False, "file_count": 0, "sha256": _canonical_hash([]), "files": []}
    if resolved.is_file():
        paths = [resolved]
        root = resolved.parent
    else:
        root = resolved
        paths = sorted(
            path
            for path in resolved.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_SUFFIXES
            and path.resolve() not in excluded
        )
    files = [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_bytes(path.read_bytes()),
        }
        for path in paths
    ]
    return {
        "exists": True,
        "file_count": len(files),
        "sha256": _canonical_hash(files),
        "files": files,
    }


def build_fingerprints(
    *,
    dataset_sha256: str,
    corpus_sha256: str,
    top_k: int,
    cutoffs: tuple[int, ...],
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """Separate comparison invariants from the treatment configuration."""

    protocol = {
        "dataset_sha256": dataset_sha256,
        "corpus_sha256": corpus_sha256,
        "top_k": top_k,
        "cutoffs": list(cutoffs),
        "metric_contract_version": 3,
        "latency_runs": configuration.get("latency_runs"),
        "warmup_runs": configuration.get("warmup_runs"),
        "cold_cache": configuration.get("cold_cache"),
    }
    treatment = {
        "chunk_size": configuration.get("chunk_size"),
        "chunk_overlap": configuration.get("chunk_overlap"),
        "semantic_chunking_enabled": configuration.get("semantic_chunking_enabled"),
        "embedding_model": configuration.get("embedding_model"),
        "vector_backend": configuration.get("vector_backend"),
        "hybrid_search_enabled": configuration.get("hybrid_search_enabled"),
        "hybrid_alpha": configuration.get("hybrid_alpha"),
        "reranker_enabled": configuration.get("reranker_enabled"),
        "reranker_model": configuration.get("reranker_model"),
        "huggingface_revision": configuration.get("huggingface_revision"),
        "huggingface_device": configuration.get("huggingface_device"),
    }
    return {
        "protocol": protocol,
        "protocol_sha256": _canonical_hash(protocol),
        "treatment": treatment,
        "treatment_sha256": _canonical_hash(treatment),
    }


def comparison_compatibility(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Require identical evaluation protocol while allowing treatment A/B changes."""

    baseline_fingerprints = baseline.get("fingerprints")
    candidate_fingerprints = candidate.get("fingerprints")
    if not isinstance(baseline_fingerprints, dict) or not isinstance(candidate_fingerprints, dict):
        return False, ["missing_fingerprints"]
    baseline_protocol = baseline_fingerprints.get("protocol")
    candidate_protocol = candidate_fingerprints.get("protocol")
    if not isinstance(baseline_protocol, dict) or not isinstance(candidate_protocol, dict):
        return False, ["missing_protocol_fingerprint"]
    differences = [
        key
        for key in sorted(set(baseline_protocol) | set(candidate_protocol))
        if baseline_protocol.get(key) != candidate_protocol.get(key)
    ]
    hashes_match = baseline_fingerprints.get("protocol_sha256") == candidate_fingerprints.get(
        "protocol_sha256"
    )
    return hashes_match and not differences, differences


def treatment_differences(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_treatment = baseline.get("fingerprints", {}).get("treatment", {})
    candidate_treatment = candidate.get("fingerprints", {}).get("treatment", {})
    if not isinstance(baseline_treatment, dict) or not isinstance(candidate_treatment, dict):
        return {}
    return {
        key: {"baseline": baseline_treatment.get(key), "candidate": candidate_treatment.get(key)}
        for key in sorted(set(baseline_treatment) | set(candidate_treatment))
        if baseline_treatment.get(key) != candidate_treatment.get(key)
    }
