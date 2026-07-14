"""Quality gate and baseline regression evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.provenance import comparison_compatibility


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "failures": list(self.failures), "checks": list(self.checks)}


def _number(payload: dict[str, Any], dotted_path: str) -> float | None:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        return float(current)
    return None


def load_thresholds(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid_threshold_file:{path}")
    return payload


def evaluate_gates(
    report: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    max_regression: float = 0.0,
) -> GateResult:
    failures: list[str] = []
    checks: list[str] = []
    configured_top_k = report.get("configuration", {}).get("top_k", 5)
    metric_depth = int(configured_top_k) if isinstance(configured_top_k, int) else 5
    def metric_path(value: object) -> str:
        return str(value).replace("{k}", str(metric_depth))
    minimums = dict(thresholds.get("minimums", {})) if isinstance(thresholds.get("minimums"), dict) else {}
    maximums = dict(thresholds.get("maximums", {})) if isinstance(thresholds.get("maximums"), dict) else {}
    conditional = thresholds.get("conditional", {})
    if isinstance(conditional, dict):
        for section, rules in conditional.items():
            if section not in report or not isinstance(rules, dict):
                continue
            section_minimums = rules.get("minimums", {})
            section_maximums = rules.get("maximums", {})
            if isinstance(section_minimums, dict):
                minimums.update(section_minimums)
            if isinstance(section_maximums, dict):
                maximums.update(section_maximums)
    for raw_path, expected in sorted(minimums.items()):
        path = metric_path(raw_path)
        actual = _number(report, str(path))
        checks.append(f"{path} >= {expected}")
        if actual is None or actual < float(expected):
            failures.append(f"{path}: expected >= {expected}, got {actual}")
    for raw_path, expected in sorted(maximums.items()):
        path = metric_path(raw_path)
        actual = _number(report, str(path))
        checks.append(f"{path} <= {expected}")
        if actual is None or actual > float(expected):
            failures.append(f"{path}: expected <= {expected}, got {actual}")

    regression_metrics = thresholds.get("regression_metrics", [])
    if baseline is not None and isinstance(regression_metrics, list):
        compatible, differences = comparison_compatibility(baseline, report)
        checks.append("baseline protocol fingerprint matches candidate")
        if not compatible:
            failures.append(f"baseline_incompatible: {','.join(differences) or 'fingerprint_mismatch'}")
            return GateResult(passed=False, failures=tuple(failures), checks=tuple(checks))
        for raw_path in regression_metrics:
            path = metric_path(raw_path)
            actual = _number(report, path)
            previous = _number(baseline, path)
            checks.append(f"{path} regression <= {max_regression}")
            if actual is None or previous is None:
                failures.append(f"{path}: missing current or baseline value")
            elif previous - actual > max_regression:
                failures.append(
                    f"{path}: regressed by {round(previous - actual, 6)} "
                    f"(baseline={previous}, current={actual})"
                )
    return GateResult(passed=not failures, failures=tuple(failures), checks=tuple(checks))
