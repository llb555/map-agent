"""Download or verify the Hugging Face models configured for Arcadegent RAG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings
from app.rag.service import SentenceTransformerEmbeddings, SentenceTransformerReranker


def _model_id(value: str, *, label: str) -> str:
    prefix = "sentence-transformers:"
    if not value.startswith(prefix) or not value[len(prefix) :].strip():
        raise ValueError(f"{label}_must_use_sentence_transformers_prefix")
    return value[len(prefix) :].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-model", help="Override RAG_EMBEDDING_MODEL.")
    parser.add_argument("--reranker-model", help="Override RAG_RERANKER_MODEL and verify it too.")
    parser.add_argument("--text", default="Gamma Arcade 的机器维护状态比较稳定")
    parser.add_argument("--query", default="Gamma Arcade 维护怎么样")
    parser.add_argument("--offline", action="store_true", help="Require an already cached model.")
    args = parser.parse_args()

    settings = Settings.from_env()
    embedding_model = args.embedding_model or settings.rag_embedding_model
    started = perf_counter()
    try:
        embedder = SentenceTransformerEmbeddings(
            model_name=_model_id(embedding_model, label="embedding_model"),
            cache_dir=settings.huggingface_cache_dir,
            token=settings.huggingface_token,
            device=settings.huggingface_device,
            offline=args.offline or settings.huggingface_offline,
            trust_remote_code=settings.huggingface_trust_remote_code,
            revision=settings.huggingface_revision,
        )
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    vector = embedder.embed_query(args.text)
    report: dict[str, object] = {
        "embedding_model": embedding_model,
        "embedding_dimensions": len(vector),
        "embedding_nonzero": any(value != 0 for value in vector),
        "cache_dir": str(settings.huggingface_cache_dir),
        "offline": args.offline or settings.huggingface_offline,
        "device": settings.huggingface_device or "auto",
    }

    reranker_model = args.reranker_model or (
        settings.rag_reranker_model if settings.rag_reranker_enabled else ""
    )
    if reranker_model:
        try:
            reranker = SentenceTransformerReranker(
                model_name=_model_id(reranker_model, label="reranker_model"),
                timeout_seconds=settings.rag_reranker_timeout_seconds,
                cache_dir=settings.huggingface_cache_dir,
                device=settings.huggingface_device,
                offline=args.offline or settings.huggingface_offline,
                trust_remote_code=settings.huggingface_trust_remote_code,
                revision=settings.huggingface_revision,
            )
        except (RuntimeError, ValueError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        ranked = reranker.rerank(
            args.query,
            [
                {"title": "relevant", "snippet": args.text, "score": 0.0},
                {"title": "irrelevant", "snippet": "今天适合散步", "score": 0.0},
            ],
            top_k=2,
        )
        report["reranker_model"] = reranker_model
        report["reranker_order"] = [item["title"] for item in ranked]
    report["duration_ms"] = round((perf_counter() - started) * 1000, 3)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["embedding_nonzero"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
