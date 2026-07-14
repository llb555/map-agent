"""Run reproducible RAG retrieval, tool-boundary, and answer evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from time import perf_counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = BACKEND_ROOT.parent
EVALUATION_ROOT = BACKEND_ROOT / "evaluation"
BUNDLED_DATASET = EVALUATION_ROOT / "datasets" / "arcadegent_demo_v2.json"
BUNDLED_KNOWLEDGE = EVALUATION_ROOT / "fixtures" / "knowledge"
DEFAULT_THRESHOLDS = EVALUATION_ROOT / "thresholds.json"
LOCAL_DATASET = REPO_ROOT / "data" / "local" / "knowledge" / "eval_queries.json"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.tools.builtin import BuiltinToolProvider
from app.agent.tools.mcp_gateway import MCPToolGateway
from app.agent.tools.permission import ToolPermissionChecker
from app.agent.tools.registry import ToolRegistry
from app.core.config import Settings
from app.evaluation.evaluator import evaluate_answers, evaluate_retrieval, evaluate_tool_calls
from app.evaluation.gates import evaluate_gates, load_thresholds
from app.evaluation.generation import generate_grounded_answers
from app.evaluation.judge import evaluate_with_judge
from app.evaluation.models import load_dataset, load_predictions
from app.evaluation.provenance import build_fingerprints, knowledge_manifest
from app.evaluation.reporting import write_json_report, write_markdown_report
from app.infra.llm.openai_compatible_client import OpenAICompatibleClient, OpenAICompatibleConfig
from app.rag.service import LangChainRAGService


def _path(value: str | None, *, default: Path | None = None) -> Path | None:
    if not value:
        return default
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


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


def _default_dataset() -> Path:
    return LOCAL_DATASET if LOCAL_DATASET.exists() else BUNDLED_DATASET


def _settings(args: argparse.Namespace, dataset_path: Path) -> Settings:
    settings = Settings.from_env()
    requested_source = _path(args.source_path)
    if requested_source is None and dataset_path == BUNDLED_DATASET:
        requested_source = BUNDLED_KNOWLEDGE
    overrides: dict[str, object] = {
        "rag_enabled": True,
        "rag_query_cache_enabled": not args.disable_cache,
    }
    if requested_source is not None:
        overrides["rag_source_path"] = requested_source
    if args.embedding_model:
        overrides["rag_embedding_model"] = args.embedding_model
    elif dataset_path == BUNDLED_DATASET:
        overrides["rag_embedding_model"] = "local-hash-v1"
    if args.vector_backend:
        overrides["rag_vector_backend"] = args.vector_backend
    if args.hybrid:
        overrides["rag_hybrid_search_enabled"] = True
    if args.reranker:
        overrides["rag_reranker_enabled"] = True
        overrides["rag_reranker_model"] = args.reranker
    return replace(settings, **overrides)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", help="Versioned JSON evaluation dataset. Uses local labels when present.")
    parser.add_argument("--source-path", help="Knowledge file or directory; defaults to RAG_SOURCE_PATH.")
    parser.add_argument("--predictions", help="Optional JSON file containing generated answers and citations.")
    parser.add_argument(
        "--generate-answers",
        action="store_true",
        help="Generate grounded answers from the retrieved contexts before scoring (cost-bearing).",
    )
    parser.add_argument("--answer-model", help="Override LLM_MODEL for answer generation.")
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Use the configured OpenAI-compatible model to judge answer predictions (opt-in/cost-bearing).",
    )
    parser.add_argument("--judge-model", help="Override LLM_MODEL for judge calls.")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum retrieval depth (1-8).")
    parser.add_argument("--cutoffs", default="1,3,5", help="Comma-separated metric cutoffs.")
    parser.add_argument("--embedding-model", help="Override RAG_EMBEDDING_MODEL for this run.")
    parser.add_argument("--vector-backend", choices=("memory", "faiss"), help="Override vector backend.")
    parser.add_argument("--hybrid", action="store_true", help="Enable vector and BM25 hybrid retrieval.")
    parser.add_argument("--reranker", help="Enable the specified reranker model.")
    parser.add_argument("--cold-cache", action="store_true", help="Clear query cache before every case.")
    parser.add_argument("--latency-runs", type=int, default=1, help="Measured retrieval runs per case.")
    parser.add_argument("--warmup-runs", type=int, default=0, help="Unmeasured warmup runs per case.")
    parser.add_argument("--disable-cache", action="store_true", help="Disable retrieval result caching.")
    parser.add_argument("--skip-tool-eval", action="store_true", help="Skip tool registry boundary checks.")
    parser.add_argument("--thresholds", help="Quality-gate JSON; defaults to bundled thresholds.")
    parser.add_argument("--baseline", help="Previous JSON report used for regression checks.")
    parser.add_argument("--max-regression", type=float, default=0.02, help="Allowed absolute metric regression.")
    parser.add_argument(
        "--output-dir",
        default="data/runtime/rag-evaluation",
        help="Directory for timestamped JSON and Markdown reports.",
    )
    parser.add_argument("--run-name", default="rag-eval", help="Human-readable report filename prefix.")
    parser.add_argument("--fail-on-gate", action="store_true", help="Return exit code 2 when a gate fails.")
    return parser


def _cutoffs(raw: str, top_k: int) -> tuple[int, ...]:
    try:
        values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    except ValueError as exc:
        raise ValueError(f"invalid_cutoffs:{raw}") from exc
    if not values or values[0] < 1 or values[-1] > top_k:
        raise ValueError(f"cutoffs_must_be_between_1_and_top_k:{raw}")
    return values


def main() -> int:
    args = _parser().parse_args()
    dataset_path = _path(args.dataset, default=_default_dataset())
    assert dataset_path is not None
    dataset = load_dataset(dataset_path)
    top_k = max(1, min(8, args.top_k))
    cutoffs = _cutoffs(args.cutoffs, top_k)
    settings = _settings(args, dataset_path)
    excluded_source_paths = {dataset_path.resolve()}
    prediction_candidate = _path(args.predictions)
    if prediction_candidate is not None:
        excluded_source_paths.add(prediction_candidate.resolve())
    service = LangChainRAGService(
        settings=settings,
        project_root=BACKEND_ROOT / "app",
        excluded_source_paths=excluded_source_paths,
    )
    dataset_sha256 = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    corpus = knowledge_manifest(settings.rag_source_path, excluded_paths=excluded_source_paths)
    configuration = {
        "source_path": str(settings.rag_source_path),
        "top_k": top_k,
        "cutoffs": list(cutoffs),
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "semantic_chunking_enabled": settings.rag_semantic_chunking_enabled,
        "embedding_model": settings.rag_embedding_model,
        "vector_backend": settings.rag_vector_backend,
        "hybrid_search_enabled": settings.rag_hybrid_search_enabled,
        "hybrid_alpha": settings.rag_hybrid_alpha,
        "reranker_enabled": settings.rag_reranker_enabled,
        "reranker_model": settings.rag_reranker_model,
        "huggingface_revision": settings.huggingface_revision or "default",
        "huggingface_device": settings.huggingface_device or "auto",
        "huggingface_offline": settings.huggingface_offline,
        "cold_cache": args.cold_cache,
        "latency_runs": max(1, args.latency_runs),
        "warmup_runs": max(0, args.warmup_runs),
    }

    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    preparation_started = perf_counter()
    preparation_health = service.warmup()
    preparation_ms = (perf_counter() - preparation_started) * 1000
    report: dict[str, object] = {
        "schema_version": 2,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "name": dataset.name,
            "version": dataset.version,
            "description": dataset.description,
            "path": str(dataset_path),
            "sha256": dataset_sha256,
            "case_count": len(dataset.cases),
        },
        "corpus": corpus,
        "configuration": configuration,
        "fingerprints": build_fingerprints(
            dataset_sha256=dataset_sha256,
            corpus_sha256=str(corpus["sha256"]),
            top_k=top_k,
            cutoffs=cutoffs,
            configuration=configuration,
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "index_preparation": {
            "duration_ms": round(preparation_ms, 3),
            "index_ready": bool(preparation_health.get("index_ready")),
            "chunk_count": int(preparation_health.get("chunk_count") or 0),
            "load_error": preparation_health.get("load_error"),
        },
        "retrieval": evaluate_retrieval(
            dataset,
            service,
            top_k=top_k,
            cutoffs=cutoffs,
            cold_cache=args.cold_cache,
            latency_runs=max(1, args.latency_runs),
            warmup_runs=max(0, args.warmup_runs),
        ),
        "rag_health": service.health(),
    }
    if not args.skip_tool_eval:
        report["tool"] = evaluate_tool_calls(dataset, _build_tool_registry(settings, service), top_k=top_k)
    prediction_path = _path(args.predictions)
    if args.generate_answers and prediction_path is not None:
        raise ValueError("choose_predictions_or_generate_answers")
    if args.llm_judge and prediction_path is None:
        if not args.generate_answers:
            raise ValueError("llm_judge_requires_predictions_or_generate_answers")
    predictions = load_predictions(prediction_path) if prediction_path is not None else None
    if args.generate_answers:
        answer_client = OpenAICompatibleClient(
            OpenAICompatibleConfig(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=args.answer_model or settings.llm_model,
                timeout_seconds=settings.llm_timeout_seconds,
                temperature=0.0,
                max_tokens=settings.llm_max_tokens,
            )
        )
        predictions, generation_report = generate_grounded_answers(
            dataset,
            report["retrieval"],  # type: ignore[arg-type]
            answer_client,
        )
        report["generation"] = generation_report
    if predictions is not None:
        report["answers"] = evaluate_answers(dataset, predictions)
        if args.llm_judge:
            judge_client = OpenAICompatibleClient(
                OpenAICompatibleConfig(
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    model=args.judge_model or settings.llm_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                    temperature=0.0,
                    max_tokens=min(500, settings.llm_max_tokens),
                )
            )
            report["llm_judge"] = evaluate_with_judge(
                dataset,
                predictions,
                report["retrieval"],  # type: ignore[arg-type]
                judge_client,
            )

    threshold_path = _path(args.thresholds, default=DEFAULT_THRESHOLDS)
    baseline_path = _path(args.baseline)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path else None
    thresholds = load_thresholds(threshold_path)
    if args.skip_tool_eval and isinstance(thresholds.get("minimums"), dict):
        thresholds = {
            **thresholds,
            "minimums": {
                path: value
                for path, value in thresholds["minimums"].items()
                if not str(path).startswith("tool.")
            },
        }
    gate = evaluate_gates(
        report,
        thresholds=thresholds,
        baseline=baseline if isinstance(baseline, dict) else None,
        max_regression=max(0.0, args.max_regression),
    )
    report["gate"] = gate.to_dict()

    output_dir = _path(args.output_dir)
    assert output_dir is not None
    json_path = output_dir / f"{args.run_name}-{run_id}.json"
    markdown_path = output_dir / f"{args.run_name}-{run_id}.md"
    write_json_report(report, json_path)
    write_markdown_report(report, markdown_path)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "gate_passed": gate.passed,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "retrieval_metrics": report["retrieval"]["metrics"],  # type: ignore[index]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 2 if args.fail_on_gate and not gate.passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
