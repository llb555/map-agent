"""Evaluate local RAG hit accuracy and knowledge_search_tool success rate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.tools.builtin import BuiltinToolProvider
from app.agent.tools.mcp_gateway import MCPToolGateway
from app.agent.tools.permission import ToolPermissionChecker
from app.agent.tools.registry import ToolRegistry
from app.core.config import Settings
from app.rag.service import LangChainRAGService


@dataclass(frozen=True)
class EvalCase:
    """One local retrieval evaluation case."""

    case_id: str
    query: str
    expected_title: str
    expected_snippet_substring: str | None = None


def _load_cases(dataset_path: Path) -> list[EvalCase]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", payload if isinstance(payload, list) else [])
    if not isinstance(raw_cases, list):
        raise ValueError(f"invalid_eval_dataset:{dataset_path}")
    cases: list[EvalCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        expected_title = str(item.get("expected_title") or "").strip()
        if not query or not expected_title:
            continue
        cases.append(
            EvalCase(
                case_id=str(item.get("id") or f"case_{len(cases)+1}"),
                query=query,
                expected_title=expected_title,
                expected_snippet_substring=str(item.get("expected_snippet_substring") or "").strip() or None,
            )
        )
    if not cases:
        raise ValueError(f"empty_eval_cases:{dataset_path}")
    return cases


def _build_tool_registry(settings: Settings, rag_service: LangChainRAGService) -> ToolRegistry:
    gateway = MCPToolGateway()
    provider = BuiltinToolProvider(
        runtime_services={
            "settings": settings,
            "project_root": BACKEND_ROOT / "app",
            "mcp_tool_gateway": gateway,
            "knowledge_rag_service": rag_service,
        }
    )
    return ToolRegistry(
        providers=[provider],
        permission_checker=ToolPermissionChecker(policy_file=BACKEND_ROOT / "missing-tool-policy.yaml"),
        strict_schema=True,
    )


def _evaluate_service(cases: list[EvalCase], rag_service: LangChainRAGService, *, top_k: int) -> dict[str, Any]:
    top1_correct = 0
    hit_at_k = 0
    snippet_match = 0
    rows: list[dict[str, Any]] = []

    for case in cases:
        result = rag_service.search(query=case.query, top_k=top_k)
        hits = result.get("hits") if isinstance(result, dict) else None
        hits = hits if isinstance(hits, list) else []
        hit_titles = [str(item.get("title") or "") for item in hits if isinstance(item, dict)]
        top_title = hit_titles[0] if hit_titles else None
        matched_titles = case.expected_title in hit_titles
        matched_top1 = top_title == case.expected_title
        matched_snippet = False
        if case.expected_snippet_substring:
            for item in hits:
                if not isinstance(item, dict):
                    continue
                if str(item.get("title") or "") != case.expected_title:
                    continue
                snippet = str(item.get("snippet") or "")
                if case.expected_snippet_substring in snippet:
                    matched_snippet = True
                    break

        top1_correct += int(matched_top1)
        hit_at_k += int(matched_titles)
        snippet_match += int(matched_snippet)
        rows.append(
            {
                "id": case.case_id,
                "query": case.query,
                "expected_title": case.expected_title,
                "top_title": top_title,
                "matched_top1": matched_top1,
                "matched_hit_at_k": matched_titles,
                "matched_snippet": matched_snippet,
                "hit_count": len(hits),
            }
        )

    total = len(cases)
    return {
        "total_cases": total,
        "top1_accuracy": round(top1_correct / total, 4),
        "hit_at_k_accuracy": round(hit_at_k / total, 4),
        "snippet_match_rate": round(snippet_match / total, 4),
        "rows": rows,
    }


def _evaluate_tool_calls(cases: list[EvalCase], registry: ToolRegistry, *, top_k: int) -> dict[str, Any]:
    completed = 0
    completed_with_hits = 0
    rows: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        result = _run_async(
            registry.execute(
                call_id=f"eval_{index}",
                tool_name="knowledge_search_tool",
                raw_arguments={"query": case.query, "top_k": top_k},
                allowed_tools=["knowledge_search_tool"],
            )
        )
        is_completed = result.status == "completed"
        hits = result.output.get("hits") if isinstance(result.output, dict) else None
        hit_count = len(hits) if isinstance(hits, list) else 0
        completed += int(is_completed)
        completed_with_hits += int(is_completed and hit_count > 0)
        rows.append(
            {
                "id": case.case_id,
                "query": case.query,
                "status": result.status,
                "hit_count": hit_count,
                "error_message": result.error_message,
            }
        )

    total = len(cases)
    return {
        "total_cases": total,
        "tool_call_success_rate": round(completed / total, 4),
        "tool_call_nonempty_hit_rate": round(completed_with_hits / total, 4),
        "rows": rows,
    }


def _run_async(awaitable: Any) -> Any:
    import asyncio

    return asyncio.run(awaitable)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="data/local/knowledge/eval_queries.json",
        help="Path to the local evaluation dataset JSON file.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Top-k retrieval window used for both service and tool evaluation.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPO_ROOT / dataset_path

    settings = Settings.from_env()
    rag_service = LangChainRAGService(settings=settings, project_root=BACKEND_ROOT / "app")
    registry = _build_tool_registry(settings=settings, rag_service=rag_service)
    cases = _load_cases(dataset_path)

    report = {
        "dataset": str(dataset_path),
        "service_eval": _evaluate_service(cases, rag_service, top_k=max(1, args.top_k)),
        "tool_eval": _evaluate_tool_calls(cases, registry, top_k=max(1, args.top_k)),
        "rag_health": rag_service.health(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
