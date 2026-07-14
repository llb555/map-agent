"""Compare two RAG evaluation reports and emit metric deltas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.provenance import comparison_compatibility, treatment_differences


DEFAULT_METRICS = (
    "retrieval.metrics.hit_rate@1",
    "retrieval.metrics.hit_rate@{k}",
    "retrieval.metrics.reciprocal_rank@{k}",
    "retrieval.metrics.ndcg@{k}",
    "retrieval.metrics.context_fact_recall",
    "retrieval.latency_ms.p95",
)


def _value(payload: dict[str, Any], path: str) -> float | None:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return float(current) if isinstance(current, (int, float)) and not isinstance(current, bool) else None


def compare_reports(
    baseline: dict[str, Any], candidate: dict[str, Any], metrics: tuple[str, ...]
) -> dict[str, Any]:
    rows = []
    for path in metrics:
        before = _value(baseline, path)
        after = _value(candidate, path)
        rows.append(
            {
                "metric": path,
                "baseline": before,
                "candidate": after,
                "delta": round(after - before, 6) if before is not None and after is not None else None,
            }
        )
    compatible, incompatibilities = comparison_compatibility(baseline, candidate)
    return {
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "compatible": compatible,
        "incompatibilities": incompatibilities,
        "treatment_differences": treatment_differences(baseline, candidate),
        "metrics": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--output")
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    configured_top_k = candidate.get("configuration", {}).get("top_k", 5)
    depth = int(configured_top_k) if isinstance(configured_top_k, int) else 5
    metrics = tuple(
        item.strip().replace("{k}", str(depth))
        for item in args.metrics.split(",")
        if item.strip()
    )
    comparison = compare_reports(baseline, candidate, metrics)
    rendered = json.dumps(comparison, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if comparison["compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
