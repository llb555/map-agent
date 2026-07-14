"""JSON and concise Markdown output for RAG evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _percent(value: object) -> str:
    return f"{float(value) * 100:.2f}%" if isinstance(value, (int, float)) else "-"


def build_markdown_report(report: dict[str, Any]) -> str:
    retrieval = report.get("retrieval", {})
    metrics = retrieval.get("metrics", {}) if isinstance(retrieval, dict) else {}
    latency = retrieval.get("latency_ms", {}) if isinstance(retrieval, dict) else {}
    preparation = report.get("index_preparation", {})
    configured_depth = report.get("configuration", {}).get("top_k", 5)
    depth = int(configured_depth) if isinstance(configured_depth, int) else 5
    lines = [
        f"# RAG Evaluation: {report.get('dataset', {}).get('name', 'unknown')}",
        "",
        f"- Run ID: `{report.get('run_id', '-')}`",
        f"- Dataset version: `{report.get('dataset', {}).get('version', '-')}`",
        f"- Protocol fingerprint: `{report.get('fingerprints', {}).get('protocol_sha256', '-')}`",
        f"- Cases: `{retrieval.get('case_count', 0)}`",
        f"- Quality gate: `{'PASS' if report.get('gate', {}).get('passed') else 'FAIL'}`",
        "",
        "## Retrieval",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    preferred = [
        "hit_rate@1",
        "hit_rate@3",
        "hit_rate@5",
        "recall@5",
        f"reciprocal_rank@{depth}",
        f"average_precision@{depth}",
        f"ndcg@{depth}",
        "context_fact_recall",
    ]
    for name in preferred:
        if name in metrics:
            lines.append(f"| `{name}` | {_percent(metrics[name])} |")
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            "| Metric | Milliseconds |",
            "|---|---:|",
            f"| Mean | {float(latency.get('mean', 0)):.2f} |",
            f"| P50 | {float(latency.get('p50', 0)):.2f} |",
            f"| P95 | {float(latency.get('p95', 0)):.2f} |",
            f"| Index preparation | {float(preparation.get('duration_ms', 0)):.2f} |",
        ]
    )
    answer = report.get("answers")
    if isinstance(answer, dict):
        lines.extend(["", "## Answers", "", "| Metric | Value |", "|---|---:|"])
        for name, value in sorted(answer.get("metrics", {}).items()):
            lines.append(f"| `{name}` | {_percent(value)} |")
        missing_predictions = answer.get("missing_prediction_ids", [])
        if missing_predictions:
            lines.extend(
                [
                    "",
                    "Missing predictions: "
                    + ", ".join(f"`{case_id}`" for case_id in missing_predictions),
                ]
            )
    generation = report.get("generation")
    if isinstance(generation, dict):
        generation_latency = generation.get("latency_ms", {})
        lines.extend(
            [
                "",
                "## Generation",
                "",
                f"- Completion rate: {_percent(generation.get('completed_rate'))}",
                f"- Mean latency: {float(generation_latency.get('mean', 0)):.2f} ms",
                f"- P95 latency: {float(generation_latency.get('p95', 0)):.2f} ms",
            ]
        )
    judge = report.get("llm_judge")
    if isinstance(judge, dict):
        lines.extend(["", "## LLM Judge", "", "| Metric | Value |", "|---|---:|"])
        for name, value in sorted(judge.get("metrics", {}).items()):
            lines.append(f"| `{name}` | {_percent(value)} |")
    slices = retrieval.get("slices", {}) if isinstance(retrieval, dict) else {}
    if slices:
        lines.extend(
            [
                "",
                "## Slices",
                "",
                f"| Tag | Cases | Hit@{depth} | MRR@{depth} |",
                "|---|---:|---:|---:|",
            ]
        )
        for tag, value in slices.items():
            slice_metrics = value.get("metrics", {})
            hit = slice_metrics.get(f"hit_rate@{depth}", 0)
            reciprocal_rank = slice_metrics.get(f"reciprocal_rank@{depth}", 0)
            lines.append(
                f"| `{tag}` | {value.get('case_count', 0)} | {_percent(hit)} | "
                f"{_percent(reciprocal_rank)} |"
            )
    failures = report.get("gate", {}).get("failures", [])
    if failures:
        lines.extend(["", "## Gate Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    failed_cases = retrieval.get("failed_case_ids", []) if isinstance(retrieval, dict) else []
    if failed_cases:
        lines.extend(["", "## Cases To Inspect", "", ", ".join(f"`{case_id}`" for case_id in failed_cases)])
    return "\n".join(lines) + "\n"


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(report), encoding="utf-8")
