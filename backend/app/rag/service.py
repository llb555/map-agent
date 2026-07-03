"""LangChain-backed lightweight RAG service for knowledge retrieval."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any
import hashlib
import re
from collections import Counter
from collections import OrderedDict
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class _ChunkRecord:
    """One indexed knowledge chunk with its embedding and metadata."""

    chunk_id: str
    title: str
    source_uri: str
    source_type: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _SimpleDocument:
    """Minimal document shape used when LangChain packages are unavailable."""

    page_content: str
    metadata: dict[str, Any]


class OpenAICompatibleEmbeddings:
    """Minimal embeddings client compatible with OpenAI-style `/embeddings` APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.strip()
        self._model = model.strip()
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    @property
    def enabled(self) -> bool:
        return bool(self._base_url and self._model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            return []
        vectors = self._embed([text])
        return vectors[0] if vectors else []

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not self.enabled:
            raise RuntimeError("rag_embeddings_not_configured")
        endpoint = self._base_url.rstrip("/") + "/embeddings"
        payload = {
            "model": self._model,
            "input": texts,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = httpx.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:240] if exc.response is not None else ""
            raise RuntimeError(
                f"rag_embeddings_http_error:{exc.response.status_code if exc.response is not None else 'unknown'}:{detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"rag_embeddings_request_error:{exc}") from exc

        try:
            decoded = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("rag_embeddings_invalid_json") from exc

        rows = decoded.get("data")
        if not isinstance(rows, list):
            raise RuntimeError("rag_embeddings_invalid_response")

        vectors: list[list[float]] = []
        for item in rows:
            if not isinstance(item, dict):
                raise RuntimeError("rag_embeddings_invalid_item")
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise RuntimeError("rag_embeddings_missing_vector")
            vector = [float(value) for value in embedding]
            vectors.append(vector)

        if len(vectors) != len(texts):
            raise RuntimeError("rag_embeddings_size_mismatch")
        return vectors


class LocalHashEmbeddings:
    """Deterministic local embedding fallback for small-scale RAG demos."""

    def __init__(self, *, dimensions: int = 256) -> None:
        self._dimensions = max(64, int(dimensions))

    @property
    def enabled(self) -> bool:
        return True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        normalized = text.strip().lower()
        if not normalized:
            return [0.0] * self._dimensions
        vector = [0.0] * self._dimensions
        for token in self._tokens(normalized):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]

    def _tokens(self, text: str) -> list[str]:
        latin_tokens = [token for token in re.split(r"[\s,.;!?/\\|:_-]+", text) if token]
        cjk_chars = [char for char in text if "\u4e00" <= char <= "\u9fff"]
        merged = latin_tokens + cjk_chars
        return merged or [text]


class SentenceTransformerEmbeddings:
    """Local embeddings backed by sentence-transformers models."""

    def __init__(self, *, model_name: str) -> None:
        self._model_name = model_name.strip()
        if not self._model_name:
            raise RuntimeError("sentence_transformer_model_required")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "sentence_transformers_missing: install sentence-transformers and its runtime dependencies"
            ) from exc
        try:
            self._model = SentenceTransformer(self._model_name, local_files_only=True)
        except Exception:
            self._model = SentenceTransformer(self._model_name)

    @property
    def enabled(self) -> bool:
        return True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, row)) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return []
        vector = self._model.encode([text], normalize_embeddings=True)[0]
        return list(map(float, vector))


class BM25Index:
    """Lightweight BM25 implementation for hybrid search."""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._corpus: list[list[str]] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length: float = 0.0
        self._idf: dict[str, float] = {}
        self._num_docs: int = 0

    def build(self, documents: list[str]) -> None:
        """Build BM25 index from document texts."""
        self._corpus = [self._tokenize(doc) for doc in documents]
        self._doc_lengths = [len(tokens) for tokens in self._corpus]
        self._num_docs = len(self._corpus)
        self._avg_doc_length = sum(self._doc_lengths) / max(1, self._num_docs)

        # Calculate IDF for each term
        doc_freq: Counter[str] = Counter()
        for tokens in self._corpus:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq[token] += 1

        for term, freq in doc_freq.items():
            self._idf[term] = math.log((self._num_docs - freq + 0.5) / (freq + 0.5) + 1.0)

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Search and return (doc_index, score) pairs."""
        if not self._corpus:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: list[float] = []
        for doc_idx, doc_tokens in enumerate(self._corpus):
            score = 0.0
            doc_length = self._doc_lengths[doc_idx]
            term_freq: Counter[str] = Counter(doc_tokens)

            for query_term in query_tokens:
                if query_term not in term_freq:
                    continue

                tf = term_freq[query_term]
                idf = self._idf.get(query_term, 0.0)
                norm = 1.0 - self._b + self._b * (doc_length / self._avg_doc_length)
                score += idf * (tf * (self._k1 + 1.0)) / (tf + self._k1 * norm)

            scores.append(score)

        # Get top-k indices
        scored = list(enumerate(scores))
        ranked = sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]
        return ranked

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for BM25."""
        normalized = text.strip().lower()
        if not normalized:
            return []
        latin_tokens = [token for token in re.split(r"[\s,.;!?/\\|:_\-()]+", normalized) if token and len(token) > 1]
        cjk_chars = [char for char in normalized if "一" <= char <= "鿿"]
        return latin_tokens + cjk_chars


class BaseReranker:
    """Base class for reranking implementations."""

    @property
    def enabled(self) -> bool:
        raise NotImplementedError

    def rerank(self, query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        """Rerank documents and return top_k results with updated scores."""
        raise NotImplementedError


class SentenceTransformerReranker(BaseReranker):
    """Reranker using sentence-transformers cross-encoder models."""

    def __init__(self, *, model_name: str, timeout_seconds: float) -> None:
        self._model_name = model_name.strip()
        self._timeout_seconds = max(1.0, float(timeout_seconds))
        if not self._model_name:
            raise RuntimeError("reranker_model_required")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "sentence_transformers_missing: install sentence-transformers for reranking support"
            ) from exc
        try:
            self._model = CrossEncoder(self._model_name)
        except Exception:
            self._model = CrossEncoder(self._model_name, local_files_only=True)

    @property
    def enabled(self) -> bool:
        return True

    def rerank(self, query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not documents:
            return []

        # Prepare pairs for cross-encoder
        pairs = [(query, doc.get("snippet", "") or doc.get("text", "")) for doc in documents]

        # Get reranking scores
        scores = self._model.predict(pairs)

        # Combine documents with new scores
        reranked = [
            {**doc, "score": float(score), "reranked": True}
            for doc, score in zip(documents, scores, strict=False)
        ]

        # Sort by reranking score and return top_k
        return sorted(reranked, key=lambda x: x["score"], reverse=True)[:top_k]


class KeywordReranker(BaseReranker):
    """Fallback reranker based on keyword matching."""

    @property
    def enabled(self) -> bool:
        return True

    def rerank(self, query: str, documents: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not documents:
            return []

        query_tokens = set(self._tokenize(query.lower()))
        if not query_tokens:
            return documents[:top_k]

        # Score by keyword overlap
        reranked = []
        for doc in documents:
            text = (doc.get("snippet", "") or doc.get("text", "")).lower()
            doc_tokens = set(self._tokenize(text))
            overlap = len(query_tokens & doc_tokens)
            # Combine original score with keyword overlap
            original_score = doc.get("score", 0.0)
            boosted_score = original_score + (overlap * 0.1)
            reranked.append({**doc, "score": boosted_score, "reranked": True})

        return sorted(reranked, key=lambda x: x["score"], reverse=True)[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization for keyword matching."""
        latin_tokens = [token for token in re.split(r"[\s,.;!?/\\|:_-]+", text) if token]
        cjk_chars = [char for char in text if "一" <= char <= "鿿"]
        return latin_tokens + cjk_chars


class LangChainRAGService:
    """Build and query a LangChain-prepared in-memory knowledge index."""

    def __init__(self, *, settings: Settings, project_root: Path) -> None:
        self._project_root = project_root
        self._enabled = bool(settings.rag_enabled)
        self._source_path = self._resolve_source_path(project_root=project_root, source_path=settings.rag_source_path)
        self._chunk_size = max(200, int(settings.rag_chunk_size))
        self._chunk_overlap = max(0, min(int(settings.rag_chunk_overlap), self._chunk_size // 2))
        self._semantic_chunking_enabled = bool(settings.rag_semantic_chunking_enabled)
        self._top_k = max(1, int(settings.rag_top_k))
        self._vector_backend = settings.rag_vector_backend
        self._faiss_index_path = settings.rag_faiss_index_path
        self._faiss_metadata_path = settings.rag_faiss_metadata_path
        rag_embedding_model = settings.rag_embedding_model.strip()
        if rag_embedding_model.lower() == "local-hash-v1":
            self._embedder = LocalHashEmbeddings()
        elif rag_embedding_model.startswith("sentence-transformers:"):
            self._embedder = SentenceTransformerEmbeddings(
                model_name=rag_embedding_model.split(":", 1)[1].strip()
            )
        else:
            self._embedder = OpenAICompatibleEmbeddings(
                api_key=settings.rag_embedding_api_key or settings.llm_api_key,
                base_url=settings.rag_embedding_base_url or settings.llm_base_url,
                model=rag_embedding_model,
                timeout_seconds=settings.rag_embedding_timeout_seconds,
            )

        # Initialize reranker
        self._reranker_enabled = bool(settings.rag_reranker_enabled)
        self._reranker_multiplier = max(2, int(settings.rag_reranker_top_k_multiplier))
        rag_reranker_model = settings.rag_reranker_model.strip()
        if self._reranker_enabled and rag_reranker_model:
            if rag_reranker_model.startswith("sentence-transformers:"):
                self._reranker: BaseReranker | None = SentenceTransformerReranker(
                    model_name=rag_reranker_model.split(":", 1)[1].strip(),
                    timeout_seconds=settings.rag_reranker_timeout_seconds,
                )
            else:
                # Fallback to keyword-based reranker
                self._reranker = KeywordReranker()
        else:
            self._reranker = None

        # Initialize hybrid search
        self._hybrid_search_enabled = bool(settings.rag_hybrid_search_enabled)
        self._hybrid_alpha = max(0.0, min(1.0, float(settings.rag_hybrid_alpha)))
        self._query_cache_enabled = bool(settings.rag_query_cache_enabled)
        self._query_cache_max_entries = max(1, int(settings.rag_query_cache_max_entries))
        self._query_cache_ttl_seconds = max(1.0, float(settings.rag_query_cache_ttl_seconds))
        self._snapshot_path = settings.rag_snapshot_path
        self._bm25_index: BM25Index | None = BM25Index() if self._hybrid_search_enabled else None

        self._lock = Lock()
        self._index_ready = False
        self._chunk_records: list[_ChunkRecord] = []
        self._load_error: str | None = None
        self._faiss_index: Any | None = None
        self._supported_suffixes = {".md", ".txt", ".json", ".jsonl", ".pdf", ".docx", ".doc"}
        self._query_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._query_cache_hits = 0
        self._query_cache_misses = 0
        self._rag_embedding_model_signature = settings.rag_embedding_model.strip()

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "source_path": str(self._source_path),
            "source_exists": self._source_path.exists(),
            "source_is_dir": self._source_path.is_dir(),
            "supported_suffixes": sorted(self._supported_suffixes),
            "embeddings_configured": self._embedder.enabled,
            "vector_backend": self._vector_backend,
            "faiss_configured": self._vector_backend == "faiss",
            "semantic_chunking_enabled": self._semantic_chunking_enabled,
            "reranker_enabled": self._reranker_enabled,
            "reranker_configured": self._reranker is not None and self._reranker.enabled,
            "hybrid_search_enabled": self._hybrid_search_enabled,
            "bm25_configured": self._bm25_index is not None,
            "query_cache_enabled": self._query_cache_enabled,
            "query_cache_size": len(self._query_cache),
            "query_cache_hits": self._query_cache_hits,
            "query_cache_misses": self._query_cache_misses,
            "query_cache_hit_rate": self._query_cache_hit_rate(),
            "index_ready": self._index_ready,
            "chunk_count": len(self._chunk_records),
            "load_error": self._load_error,
        }

    def rebuild_index(self) -> dict[str, Any]:
        with self._lock:
            self._index_ready = False
            self._chunk_records = []
            self._load_error = None
            self._faiss_index = None
        self._ensure_index_loaded()
        return self.health()

    def warmup(self) -> dict[str, Any]:
        if not self._enabled:
            return self.health()
        if not self._embedder.enabled:
            self._load_error = "rag_embeddings_not_configured"
            return self.health()
        try:
            self._ensure_index_loaded()
        except Exception as exc:
            self._load_error = str(exc).strip() or type(exc).__name__
        return self.health()

    def knowledge_directory(self) -> Path:
        return self._source_path

    def supported_suffixes(self) -> list[str]:
        return sorted(self._supported_suffixes)

    def list_source_files(self) -> list[dict[str, Any]]:
        if not self._source_path.exists():
            return []
        if self._source_path.is_file():
            paths = [self._source_path]
        else:
            paths = sorted(
                path
                for path in self._source_path.rglob("*")
                if path.is_file() and path.suffix.lower() in self._supported_suffixes
            )
        results: list[dict[str, Any]] = []
        for path in paths:
            stat = path.stat()
            results.append(
                {
                    "name": path.name,
                    "relative_path": path.relative_to(self._source_path).as_posix()
                    if self._source_path.is_dir()
                    else path.name,
                    "suffix": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "updated_at": stat.st_mtime,
                }
            )
        return results

    def _hybrid_search(
        self, *, query: str, query_embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        """Combine vector and BM25 scores using weighted fusion."""
        if not self._chunk_records or not self._bm25_index:
            return []

        # Vector search scores
        vector_scores = self._vector_scores(query_embedding)

        # BM25 scores
        bm25_results = self._bm25_index.search(query, top_k=len(self._chunk_records))
        bm25_scores = {idx: score for idx, score in bm25_results}

        # Normalize scores to [0, 1]
        vector_scores_norm = self._normalize_scores(vector_scores)
        bm25_scores_norm = self._normalize_scores(bm25_scores)

        # Combine scores: hybrid_score = alpha * vector + (1 - alpha) * bm25
        alpha = self._hybrid_alpha
        combined_scores: dict[int, float] = {}
        all_indices = set(vector_scores_norm.keys()) | set(bm25_scores_norm.keys())

        for idx in all_indices:
            vec_score = vector_scores_norm.get(idx, 0.0)
            bm25_score = bm25_scores_norm.get(idx, 0.0)
            combined_scores[idx] = alpha * vec_score + (1.0 - alpha) * bm25_score

        # Rank by combined score
        ranked_indices = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Build candidate list
        candidates = []
        for idx, score in ranked_indices:
            if idx >= len(self._chunk_records):
                continue
            row = self._chunk_records[idx]
            candidates.append(
                {
                    "chunk_id": row.chunk_id,
                    "title": row.title,
                    "source_uri": row.source_uri,
                    "source_type": row.source_type,
                    "score": round(score, 4),
                    "snippet": self._snippet(row.text),
                    "text": row.text,
                    "metadata": row.metadata,
                }
            )

        return candidates

    def _normalize_scores(self, scores: dict[int, float]) -> dict[int, float]:
        """Min-max normalize scores to [0, 1] range."""
        if not scores:
            return {}
        values = list(scores.values())
        min_score = min(values)
        max_score = max(values)
        score_range = max_score - min_score

        if score_range <= 0:
            return {idx: 1.0 for idx in scores}

        return {idx: (score - min_score) / score_range for idx, score in scores.items()}

    def search(self, *, query: str, top_k: int | None = None) -> dict[str, Any]:
        normalized_query = query.strip()
        limit = max(1, min(int(top_k or self._top_k), 8))
        cache_key = self._query_cache_key(query=normalized_query, top_k=limit)
        cached = self._get_cached_search(cache_key)
        if cached is not None:
            return cached
        payload = {
            "backend": f"langchain_{self._vector_backend}",
            "query": {
                "text": normalized_query,
                "top_k": limit,
            },
            "hits": [],
        }
        if not self._enabled:
            payload["status"] = "disabled"
            payload["reason"] = "rag_disabled"
            return payload
        if not normalized_query:
            payload["status"] = "skipped"
            payload["reason"] = "empty_query"
            return payload
        if not self._embedder.enabled:
            payload["status"] = "unavailable"
            payload["reason"] = "rag_embeddings_not_configured"
            return payload

        try:
            self._ensure_index_loaded()
        except Exception as exc:  # pragma: no cover - surfaced via health and tool result
            message = str(exc).strip() or type(exc).__name__
            self._load_error = message
            payload["status"] = "unavailable"
            payload["reason"] = message
            return payload

        if not self._chunk_records:
            payload["status"] = "empty"
            payload["reason"] = "rag_source_empty"
            return payload

        query_embedding = self._embedder.embed_query(normalized_query)
        if not query_embedding:
            payload["status"] = "unavailable"
            payload["reason"] = "rag_query_embedding_failed"
            return payload

        # Two-stage retrieval: fetch more candidates if reranker is enabled
        use_reranker = self._reranker_enabled and self._reranker is not None and self._reranker.enabled
        retrieval_limit = limit * self._reranker_multiplier if use_reranker else limit

        # Hybrid search: combine vector and BM25 scores
        use_hybrid = self._hybrid_search_enabled and self._bm25_index is not None
        if use_hybrid:
            candidates = self._hybrid_search(
                query=normalized_query,
                query_embedding=query_embedding,
                top_k=retrieval_limit,
            )
            payload["hybrid_search"] = True
        else:
            # Pure vector search
            scored = self._rank_records_by_vector(query_embedding, top_k=retrieval_limit)
            candidates = [
                {
                    "chunk_id": row.chunk_id,
                    "title": row.title,
                    "source_uri": row.source_uri,
                    "source_type": row.source_type,
                    "score": round(score, 4),
                    "snippet": self._snippet(row.text),
                    "text": row.text,
                    "metadata": row.metadata,
                }
                for score, row in scored
            ]
            payload["hybrid_search"] = False

        # Apply reranking if enabled
        if use_reranker and candidates:
            try:
                ranked = self._reranker.rerank(query=normalized_query, documents=candidates, top_k=limit)
                payload["reranked"] = True
            except Exception as exc:
                # Fall back to original ranking on reranker error
                ranked = candidates[:limit]
                payload["reranker_error"] = str(exc)
                payload["reranked"] = False
        else:
            ranked = candidates[:limit]
            payload["reranked"] = False

        # Remove 'text' field from final output (keep only snippet)
        for hit in ranked:
            hit.pop("text", None)

        payload["status"] = "completed"
        payload["hits"] = ranked
        payload["total_hits"] = len(ranked)
        payload["cache_hit"] = False
        self._set_cached_search(cache_key, payload)
        return payload

    def _ensure_index_loaded(self) -> None:
        if self._index_ready:
            return
        with self._lock:
            if self._index_ready:
                return
            if self._vector_backend == "faiss" and self._try_restore_faiss_snapshot():
                if self._hybrid_search_enabled and self._bm25_index is not None and self._chunk_records:
                    doc_texts = [record.text for record in self._chunk_records]
                    self._bm25_index.build(doc_texts)
                self._index_ready = True
                self._load_error = None
                self._clear_query_cache()
                return
            if self._try_restore_generic_snapshot():
                if self._hybrid_search_enabled and self._bm25_index is not None and self._chunk_records:
                    doc_texts = [record.text for record in self._chunk_records]
                    self._bm25_index.build(doc_texts)
                self._index_ready = True
                self._load_error = None
                self._clear_query_cache()
                return
            documents = self._load_documents()
            chunks = self._split_documents(documents)
            if not chunks:
                self._chunk_records = []
                self._refresh_vector_backend([])
                self._persist_generic_snapshot([])
                self._index_ready = True
                self._load_error = None
                self._clear_query_cache()
                return

            prepared_chunks = [item for item in chunks if str(item.page_content).strip()]
            texts = [str(item.page_content).strip() for item in prepared_chunks]
            embeddings = self._embedder.embed_documents(texts)
            records: list[_ChunkRecord] = []
            for index, (chunk, embedding) in enumerate(zip(prepared_chunks, embeddings, strict=False), start=1):
                text = str(chunk.page_content).strip()
                if not text:
                    continue
                metadata = dict(getattr(chunk, "metadata", {}) or {})
                source_uri = str(metadata.get("source_uri") or metadata.get("source") or "knowledge://unknown")
                source_type = str(metadata.get("source_type") or "document")
                title = str(metadata.get("title") or Path(source_uri).stem or f"chunk-{index}")
                records.append(
                    _ChunkRecord(
                        chunk_id=f"chunk_{index}",
                        title=title,
                        source_uri=source_uri,
                        source_type=source_type,
                        text=text,
                        embedding=embedding,
                        metadata=metadata,
                    )
                )
            self._chunk_records = records
            self._refresh_vector_backend(records)
            self._persist_generic_snapshot(records)

            # Build BM25 index if hybrid search is enabled
            if self._hybrid_search_enabled and self._bm25_index is not None and records:
                doc_texts = [record.text for record in records]
                self._bm25_index.build(doc_texts)

            self._index_ready = True
            self._load_error = None
            self._clear_query_cache()

    def _refresh_vector_backend(self, records: list[_ChunkRecord]) -> None:
        if self._vector_backend != "faiss":
            self._faiss_index = None
            self._remove_faiss_sidecar_files()
            return
        if not records:
            self._faiss_index = None
            self._persist_faiss_sidecar([])
            return
        self._build_faiss_index(records)

    def _vector_scores(self, query_embedding: list[float]) -> dict[int, float]:
        if self._vector_backend == "faiss" and self._faiss_index is not None:
            return self._faiss_vector_scores(query_embedding)
        return {
            idx: self._cosine_similarity(query_embedding, row.embedding)
            for idx, row in enumerate(self._chunk_records)
        }

    def _rank_records_by_vector(self, query_embedding: list[float], *, top_k: int) -> list[tuple[float, _ChunkRecord]]:
        if self._vector_backend == "faiss" and self._faiss_index is not None:
            return self._faiss_rank_records(query_embedding, top_k=top_k)
        scored = [
            (self._cosine_similarity(query_embedding, row.embedding), row)
            for row in self._chunk_records
        ]
        return sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]

    def _build_faiss_index(self, records: list[_ChunkRecord]) -> None:
        faiss = self._import_faiss()
        matrix = [list(map(float, row.embedding)) for row in records if row.embedding]
        if not matrix:
            self._faiss_index = None
            self._persist_faiss_sidecar(records)
            return
        vectors = self._numpy_float32_matrix(matrix)
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._faiss_index = index
        self._persist_faiss_index(index)
        self._persist_faiss_sidecar(records)

    def _faiss_rank_records(self, query_embedding: list[float], *, top_k: int) -> list[tuple[float, _ChunkRecord]]:
        scores = self._faiss_vector_scores(query_embedding, top_k=top_k)
        ranked: list[tuple[float, _ChunkRecord]] = []
        for idx, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            if 0 <= idx < len(self._chunk_records):
                ranked.append((score, self._chunk_records[idx]))
        return ranked

    def _faiss_vector_scores(self, query_embedding: list[float], top_k: int | None = None) -> dict[int, float]:
        if self._faiss_index is None:
            return {}
        faiss = self._import_faiss()
        limit = max(1, min(top_k or len(self._chunk_records), len(self._chunk_records)))
        query = self._numpy_float32_matrix([[float(value) for value in query_embedding]])
        faiss.normalize_L2(query)
        distances, indices = self._faiss_index.search(query, limit)
        scores: dict[int, float] = {}
        if len(indices) == 0:
            return scores
        for idx, score in zip(indices[0], distances[0], strict=False):
            row_id = int(idx)
            if row_id < 0:
                continue
            scores[row_id] = float(score)
        return scores

    def _persist_faiss_index(self, index: Any) -> None:
        path = self._faiss_index_path
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss = self._import_faiss()
        faiss.write_index(index, str(path))

    def _persist_faiss_sidecar(self, records: list[_ChunkRecord]) -> None:
        meta_path = self._faiss_metadata_path
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "embedding_model_signature": self._rag_embedding_model_signature,
            "chunk_config": {
                "chunk_size": self._chunk_size,
                "chunk_overlap": self._chunk_overlap,
                "semantic_chunking_enabled": self._semantic_chunking_enabled,
            },
            "source_signature": self._source_signature(),
            "records": [
                {
                    "chunk_id": row.chunk_id,
                    "title": row.title,
                    "source_uri": row.source_uri,
                    "source_type": row.source_type,
                    "text": row.text,
                    "embedding": row.embedding,
                    "metadata": row.metadata,
                }
                for row in records
            ],
        }
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _try_restore_faiss_snapshot(self) -> bool:
        if not self._faiss_index_path.exists() or not self._faiss_metadata_path.exists():
            return False
        try:
            payload = json.loads(self._faiss_metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("version") != 1:
            return False
        if payload.get("source_signature") != self._source_signature():
            return False
        if payload.get("embedding_model_signature") != self._rag_embedding_model_signature:
            return False
        if payload.get("chunk_config") != {
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
            "semantic_chunking_enabled": self._semantic_chunking_enabled,
        }:
            return False
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            return False
        records: list[_ChunkRecord] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            embedding = item.get("embedding")
            metadata = item.get("metadata")
            text = item.get("text")
            if not isinstance(embedding, list) or not isinstance(metadata, dict) or not isinstance(text, str):
                continue
            records.append(
                _ChunkRecord(
                    chunk_id=str(item.get("chunk_id") or f"chunk_{len(records) + 1}"),
                    title=str(item.get("title") or "unknown"),
                    source_uri=str(item.get("source_uri") or "knowledge://unknown"),
                    source_type=str(item.get("source_type") or "document"),
                    text=text,
                    embedding=[float(value) for value in embedding],
                    metadata=metadata,
                )
            )
        if not records:
            return False
        faiss = self._import_faiss()
        try:
            index = faiss.read_index(str(self._faiss_index_path))
        except Exception:
            return False
        self._chunk_records = records
        self._faiss_index = index
        return True

    def _remove_faiss_sidecar_files(self) -> None:
        for path in (self._faiss_index_path, self._faiss_metadata_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue

    def _persist_generic_snapshot(self, records: list[_ChunkRecord]) -> None:
        path = self._snapshot_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "embedding_model_signature": self._rag_embedding_model_signature,
            "chunk_config": {
                "chunk_size": self._chunk_size,
                "chunk_overlap": self._chunk_overlap,
                "semantic_chunking_enabled": self._semantic_chunking_enabled,
            },
            "source_signature": self._source_signature(),
            "records": [
                {
                    "chunk_id": row.chunk_id,
                    "title": row.title,
                    "source_uri": row.source_uri,
                    "source_type": row.source_type,
                    "text": row.text,
                    "embedding": row.embedding,
                    "metadata": row.metadata,
                }
                for row in records
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _try_restore_generic_snapshot(self) -> bool:
        if not self._snapshot_path.exists():
            return False
        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("version") != 1:
            return False
        if payload.get("source_signature") != self._source_signature():
            return False
        if payload.get("embedding_model_signature") != self._rag_embedding_model_signature:
            return False
        if payload.get("chunk_config") != {
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
            "semantic_chunking_enabled": self._semantic_chunking_enabled,
        }:
            return False
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            return False
        records: list[_ChunkRecord] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            embedding = item.get("embedding")
            metadata = item.get("metadata")
            text = item.get("text")
            if not isinstance(embedding, list) or not isinstance(metadata, dict) or not isinstance(text, str):
                continue
            records.append(
                _ChunkRecord(
                    chunk_id=str(item.get("chunk_id") or f"chunk_{len(records) + 1}"),
                    title=str(item.get("title") or "unknown"),
                    source_uri=str(item.get("source_uri") or "knowledge://unknown"),
                    source_type=str(item.get("source_type") or "document"),
                    text=text,
                    embedding=[float(value) for value in embedding],
                    metadata=metadata,
                )
            )
        if not records:
            return False
        self._chunk_records = records
        return True

    def _query_cache_key(self, *, query: str, top_k: int) -> str:
        config_signature = {
            "source_signature": self._source_signature(),
            "top_k": top_k,
            "vector_backend": self._vector_backend,
            "hybrid": self._hybrid_search_enabled,
            "hybrid_alpha": self._hybrid_alpha,
            "reranker": self._reranker_enabled,
        }
        return json.dumps(
            {
                "query": query,
                "config": config_signature,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _get_cached_search(self, cache_key: str) -> dict[str, Any] | None:
        if not self._query_cache_enabled or not cache_key:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._query_cache.get(cache_key)
            if entry is None:
                self._query_cache_misses += 1
                return None
            cached_at, payload = entry
            if now - cached_at > self._query_cache_ttl_seconds:
                self._query_cache.pop(cache_key, None)
                self._query_cache_misses += 1
                return None
            self._query_cache.move_to_end(cache_key)
            self._query_cache_hits += 1
            cached = json.loads(json.dumps(payload, ensure_ascii=False))
            cached["cache_hit"] = True
            return cached

    def _set_cached_search(self, cache_key: str, payload: dict[str, Any]) -> None:
        if not self._query_cache_enabled or not cache_key:
            return
        cached = json.loads(json.dumps(payload, ensure_ascii=False))
        cached["cache_hit"] = False
        with self._lock:
            self._query_cache[cache_key] = (time.monotonic(), cached)
            self._query_cache.move_to_end(cache_key)
            while len(self._query_cache) > self._query_cache_max_entries:
                self._query_cache.popitem(last=False)

    def _clear_query_cache(self) -> None:
        with self._lock:
            self._query_cache.clear()
            self._query_cache_hits = 0
            self._query_cache_misses = 0

    def _query_cache_hit_rate(self) -> float:
        total = self._query_cache_hits + self._query_cache_misses
        if total <= 0:
            return 0.0
        return round(self._query_cache_hits / total, 4)

    def _import_faiss(self) -> Any:
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError("faiss_missing: install faiss-cpu to enable FAISS vector backend") from exc
        return faiss

    def _numpy_float32_matrix(self, rows: list[list[float]]) -> Any:
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("numpy_missing: install numpy to enable FAISS vector backend") from exc
        return np.asarray(rows, dtype="float32")

    def _source_signature(self) -> list[dict[str, Any]]:
        return self.list_source_files()

    def _load_documents(self) -> list[Any]:
        document_cls = self._document_class()

        if not self._source_path.exists():
            return []

        if self._source_path.is_file():
            paths = [self._source_path]
        else:
            paths = sorted(
                path
                for path in self._source_path.rglob("*")
                if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".jsonl", ".pdf", ".docx", ".doc"}
            )

        documents: list[Any] = []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                documents.extend(
                    self._documents_from_labeled_text(
                        text=text,
                        source_title=path.stem,
                        source_uri=str(path),
                        source_type=suffix.lstrip("."),
                        document_cls=document_cls,
                    )
                )
                continue

            if suffix == ".jsonl":
                documents.extend(self._documents_from_jsonl(path=path, document_cls=document_cls))
                continue

            if suffix == ".pdf":
                documents.extend(self._documents_from_pdf(path=path, document_cls=document_cls))
                continue

            if suffix == ".docx":
                documents.extend(self._documents_from_docx(path=path, document_cls=document_cls))
                continue

            if suffix == ".doc":
                documents.extend(self._documents_from_doc(path=path, document_cls=document_cls))
                continue

            documents.extend(self._documents_from_json(path=path, document_cls=document_cls))
        return documents

    def _documents_from_labeled_text(
        self,
        *,
        text: str,
        source_title: str,
        source_uri: str,
        source_type: str,
        document_cls: Any,
    ) -> list[Any]:
        parsed_documents = self._extract_structured_arcade_documents_from_text(
            text=text,
            source_title=source_title,
            source_uri=source_uri,
            source_type=source_type,
            document_cls=document_cls,
        )
        if parsed_documents:
            return parsed_documents
        return [
            document_cls(
                page_content=text,
                metadata={
                    "title": source_title,
                    "source_uri": source_uri,
                    "source_type": source_type,
                },
            )
        ]

    def _extract_structured_arcade_documents_from_text(
        self,
        *,
        text: str,
        source_title: str,
        source_uri: str,
        source_type: str,
        document_cls: Any,
    ) -> list[Any]:
        normalized_text = text.strip()
        if not normalized_text:
            return []

        lines = [line.strip() for line in normalized_text.splitlines()]
        documents: list[Any] = []
        current: dict[str, str] = {}
        note_lines: list[str] = []

        def flush_current() -> None:
            nonlocal current, note_lines
            name = current.get("shop_name") or current.get("name")
            address = current.get("address")
            city_name = current.get("city_name") or current.get("city")
            province_name = current.get("province_name") or current.get("province")
            county_name = current.get("county_name") or current.get("district")
            if not name or not (address or city_name or province_name or county_name):
                current = {}
                note_lines = []
                return
            content_parts = [
                f"机厅名：{name}",
                f"地址：{address}" if address else None,
                f"省份：{province_name}" if province_name else None,
                f"城市：{city_name}" if city_name else None,
                f"区县：{county_name}" if county_name else None,
                f"交通：{current.get('transport')}" if current.get("transport") else None,
                f"备注：{' '.join(note_lines).strip()}" if note_lines else None,
            ]
            documents.append(
                document_cls(
                    page_content="\n".join(part for part in content_parts if part),
                    metadata={
                        "title": name,
                        "source_uri": source_uri,
                        "source_type": source_type,
                        "shop_name": name,
                        "address": address,
                        "province_name": province_name,
                        "city_name": city_name,
                        "county_name": county_name,
                        "transport": current.get("transport"),
                    },
                )
            )
            current = {}
            note_lines = []

        label_aliases = {
            "机厅名": "shop_name",
            "店名": "shop_name",
            "场馆名": "shop_name",
            "门店名": "shop_name",
            "shop_name": "shop_name",
            "name": "shop_name",
            "地址": "address",
            "详细地址": "address",
            "address": "address",
            "省": "province_name",
            "省份": "province_name",
            "province": "province_name",
            "province_name": "province_name",
            "市": "city_name",
            "城市": "city_name",
            "city": "city_name",
            "city_name": "city_name",
            "区": "county_name",
            "区县": "county_name",
            "县区": "county_name",
            "district": "county_name",
            "county_name": "county_name",
            "交通": "transport",
            "到达方式": "transport",
            "transport": "transport",
            "备注": "note",
            "说明": "note",
            "content": "note",
            "正文": "note",
        }

        for raw_line in lines:
            if not raw_line:
                if current and note_lines:
                    note_lines.append("")
                continue
            line = raw_line.lstrip("-*0123456789. ").strip()
            if not line:
                continue
            match = re.match(r"^(?P<label>[^:：|]{1,20})[:：|]\s*(?P<value>.+)$", line)
            if match:
                raw_label = match.group("label").strip().lower()
                value = match.group("value").strip()
                field = label_aliases.get(raw_label)
                if field == "shop_name":
                    if current.get("shop_name") and any(
                        current.get(key) for key in ("address", "province_name", "city_name", "county_name", "transport")
                    ):
                        flush_current()
                    current["shop_name"] = value
                    continue
                if field in {"address", "province_name", "city_name", "county_name", "transport"}:
                    current[field] = value
                    continue
                if field == "note":
                    note_lines.append(value)
                    continue
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if len(cells) >= 2:
                    mapped_any = False
                    for index in range(0, len(cells) - 1, 2):
                        raw_label = cells[index].strip().lower()
                        value = cells[index + 1].strip()
                        field = label_aliases.get(raw_label)
                        if field == "shop_name":
                            if current.get("shop_name") and any(
                                current.get(key) for key in ("address", "province_name", "city_name", "county_name", "transport")
                            ):
                                flush_current()
                            current["shop_name"] = value
                            mapped_any = True
                        elif field in {"address", "province_name", "city_name", "county_name", "transport"}:
                            current[field] = value
                            mapped_any = True
                        elif field == "note":
                            note_lines.append(value)
                            mapped_any = True
                    if mapped_any:
                        continue
            if current:
                note_lines.append(line)

        if current:
            flush_current()
        return documents

    def _documents_from_pdf(self, *, path: Path, document_cls: Any) -> list[Any]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("pypdf_missing: install pypdf to enable PDF knowledge sources") from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise RuntimeError(f"pdf_read_failed:{path}:{exc}") from exc

        documents: list[Any] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = str(page.extract_text() or "").strip()
            except Exception as exc:
                raise RuntimeError(f"pdf_text_extract_failed:{path}:page_{page_number}:{exc}") from exc
            if not text:
                continue
            documents.extend(
                self._documents_from_labeled_text(
                    text=text,
                    source_title=f"{path.stem} - page {page_number}",
                    source_uri=f"{path}#page={page_number}",
                    source_type="pdf",
                    document_cls=document_cls,
                )
            )
        return documents

    def _documents_from_docx(self, *, path: Path, document_cls: Any) -> list[Any]:
        try:
            with ZipFile(path) as archive:
                parts = self._extract_docx_parts(archive=archive, path=path)
        except BadZipFile as exc:
            raise RuntimeError(f"docx_read_failed:{path}:invalid_zip") from exc
        except OSError as exc:
            raise RuntimeError(f"docx_read_failed:{path}:{exc}") from exc

        text = self._compose_docx_text(parts=parts)
        if not text:
            return []
        return self._documents_from_labeled_text(
            text=text,
            source_title=path.stem,
            source_uri=str(path),
            source_type="docx",
            document_cls=document_cls,
        )

    def _documents_from_doc(self, *, path: Path, document_cls: Any) -> list[Any]:
        with TemporaryDirectory(prefix="rag-doc-convert-") as temp_dir:
            converted_path = self._convert_doc_to_docx(path=path, output_dir=Path(temp_dir))
            documents = self._documents_from_docx(path=converted_path, document_cls=document_cls)

        normalized_documents: list[Any] = []
        for document in documents:
            metadata = dict(getattr(document, "metadata", {}) or {})
            metadata["title"] = path.stem
            metadata["source_uri"] = str(path)
            metadata["source_type"] = "doc"
            normalized_documents.append(
                document_cls(
                    page_content=str(getattr(document, "page_content", "")),
                    metadata=metadata,
                )
            )
        return normalized_documents

    def _convert_doc_to_docx(self, *, path: Path, output_dir: Path) -> Path:
        soffice_path = shutil.which("soffice")
        if soffice_path:
            result = subprocess.run(
                [soffice_path, "--headless", "--convert-to", "docx", "--outdir", str(output_dir), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            converted_path = output_dir / f"{path.stem}.docx"
            if result.returncode == 0 and converted_path.exists():
                return converted_path

        textutil_path = shutil.which("textutil")
        if textutil_path:
            converted_path = output_dir / f"{path.stem}.docx"
            result = subprocess.run(
                [textutil_path, "-convert", "docx", "-output", str(converted_path), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and converted_path.exists():
                return converted_path

        if soffice_path or textutil_path:
            raise RuntimeError(f"doc_conversion_failed:{path}")
        raise RuntimeError("doc_conversion_tool_missing: install soffice/libreoffice or use macOS textutil")

    def _extract_docx_parts(self, *, archive: ZipFile, path: Path) -> dict[str, list[str]]:
        part_sections: dict[str, list[str]] = {
            "body": [],
            "headers": [],
            "footers": [],
            "comments": [],
        }

        document_root = self._read_docx_xml_part(archive=archive, part_name="word/document.xml", path=path)
        body = next((child for child in list(document_root) if self._xml_local_name(child.tag) == "body"), None)
        if body is None:
            raise RuntimeError(f"docx_document_body_missing:{path}")
        part_sections["body"] = self._docx_collect_block_texts(body)

        for header_name in sorted(name for name in archive.namelist() if re.fullmatch(r"word/header\d+\.xml", name)):
            header_root = self._read_docx_xml_part(archive=archive, part_name=header_name, path=path)
            part_sections["headers"].extend(self._docx_collect_block_texts(header_root))

        for footer_name in sorted(name for name in archive.namelist() if re.fullmatch(r"word/footer\d+\.xml", name)):
            footer_root = self._read_docx_xml_part(archive=archive, part_name=footer_name, path=path)
            part_sections["footers"].extend(self._docx_collect_block_texts(footer_root))

        if "word/comments.xml" in archive.namelist():
            comments_root = self._read_docx_xml_part(archive=archive, part_name="word/comments.xml", path=path)
            part_sections["comments"] = self._docx_collect_comment_texts(comments_root)

        return part_sections

    def _compose_docx_text(self, *, parts: dict[str, list[str]]) -> str:
        sections: list[str] = []
        if parts.get("body"):
            sections.append("\n\n".join(parts["body"]).strip())
        if parts.get("headers"):
            sections.append("Headers:\n" + "\n".join(parts["headers"]).strip())
        if parts.get("footers"):
            sections.append("Footers:\n" + "\n".join(parts["footers"]).strip())
        if parts.get("comments"):
            sections.append("Comments:\n" + "\n".join(parts["comments"]).strip())
        return "\n\n".join(section for section in sections if section.strip()).strip()

    def _read_docx_xml_part(self, *, archive: ZipFile, part_name: str, path: Path) -> ElementTree.Element:
        try:
            raw_part = archive.read(part_name)
        except KeyError as exc:
            raise RuntimeError(f"docx_part_missing:{path}:{part_name}") from exc

        try:
            return ElementTree.fromstring(raw_part)
        except ElementTree.ParseError as exc:
            raise RuntimeError(f"docx_xml_parse_failed:{path}:{part_name}:{exc}") from exc

    def _docx_collect_comment_texts(self, root: ElementTree.Element) -> list[str]:
        comments: list[str] = []
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        for comment in list(root):
            if self._xml_local_name(comment.tag) != "comment":
                continue
            author = str(comment.attrib.get(f"{namespace}author") or "").strip()
            text = "\n".join(self._docx_collect_block_texts(comment)).strip()
            if not text:
                continue
            comments.append(f"{author}: {text}" if author else text)
        return comments

    def _docx_collect_block_texts(self, container: ElementTree.Element) -> list[str]:
        lines: list[str] = []
        for child in list(container):
            local_name = self._xml_local_name(child.tag)
            if local_name == "p":
                paragraph_text = self._docx_extract_paragraph_text(child)
                if paragraph_text:
                    lines.append(paragraph_text)
                continue
            if local_name == "tbl":
                table_text = self._docx_extract_table_text(child)
                if table_text:
                    lines.append(table_text)
                continue
        return lines

    def _docx_extract_paragraph_text(self, paragraph: ElementTree.Element) -> str:
        pieces: list[str] = []
        for node in paragraph.iter():
            local_name = self._xml_local_name(node.tag)
            if local_name == "t":
                pieces.append(node.text or "")
            elif local_name == "tab":
                pieces.append("\t")
            elif local_name in {"br", "cr"}:
                pieces.append("\n")
        text = "".join(pieces)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def _docx_extract_table_text(self, table: ElementTree.Element) -> str:
        rows: list[str] = []
        for row in list(table):
            if self._xml_local_name(row.tag) != "tr":
                continue
            cells: list[str] = []
            for cell in list(row):
                if self._xml_local_name(cell.tag) != "tc":
                    continue
                cell_lines = self._docx_collect_block_texts(cell)
                cell_text = " / ".join(line for line in cell_lines if line).strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows).strip()

    def _xml_local_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def _documents_from_jsonl(self, *, path: Path, document_cls: Any) -> list[Any]:
        documents: list[Any] = []
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc = self._document_from_payload(
                payload=payload,
                default_title=f"{path.stem}-{line_number}",
                source_uri=f"{path}:{line_number}",
                source_type="jsonl",
                document_cls=document_cls,
            )
            if doc is not None:
                documents.append(doc)
        return documents

    def _documents_from_json(self, *, path: Path, document_cls: Any) -> list[Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        items: list[Any]
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("documents"), list):
            items = payload["documents"]
        else:
            items = [payload]
        documents: list[Any] = []
        for index, item in enumerate(items, start=1):
            doc = self._document_from_payload(
                payload=item,
                default_title=f"{path.stem}-{index}",
                source_uri=f"{path}:{index}",
                source_type="json",
                document_cls=document_cls,
            )
            if doc is not None:
                documents.append(doc)
        return documents

    def _document_from_payload(
        self,
        *,
        payload: Any,
        default_title: str,
        source_uri: str,
        source_type: str,
        document_cls: Any,
    ) -> Any | None:
        if not isinstance(payload, dict):
            return None
        content = payload.get("content") or payload.get("text") or payload.get("body")
        if not isinstance(content, str) or not content.strip():
            return None
        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"content", "text", "body"} and value not in (None, "", [], {})
        }
        metadata["title"] = str(payload.get("title") or payload.get("name") or default_title)
        metadata["source_uri"] = str(payload.get("source_uri") or payload.get("source") or source_uri)
        metadata["source_type"] = str(payload.get("source_type") or source_type)

        explicit_name = payload.get("shop_name") or payload.get("name")
        explicit_address = payload.get("address")
        explicit_province = payload.get("province_name") or payload.get("province")
        explicit_city = payload.get("city_name") or payload.get("city")
        explicit_county = payload.get("county_name") or payload.get("district")
        explicit_transport = payload.get("transport")

        if any(value not in (None, "") for value in (explicit_name, explicit_address, explicit_province, explicit_city, explicit_county, explicit_transport)):
            metadata.setdefault("shop_name", str(explicit_name).strip() if explicit_name not in (None, "") else None)
            metadata.setdefault("address", str(explicit_address).strip() if explicit_address not in (None, "") else None)
            metadata.setdefault("province_name", str(explicit_province).strip() if explicit_province not in (None, "") else None)
            metadata.setdefault("city_name", str(explicit_city).strip() if explicit_city not in (None, "") else None)
            metadata.setdefault("county_name", str(explicit_county).strip() if explicit_county not in (None, "") else None)
            metadata.setdefault("transport", str(explicit_transport).strip() if explicit_transport not in (None, "") else None)
            return document_cls(page_content=content.strip(), metadata=metadata)

        parsed_documents = self._extract_structured_arcade_documents_from_text(
            text=content.strip(),
            source_title=str(metadata["title"]),
            source_uri=str(metadata["source_uri"]),
            source_type=str(metadata["source_type"]),
            document_cls=document_cls,
        )
        if parsed_documents:
            if len(parsed_documents) == 1:
                parsed = parsed_documents[0]
                parsed_metadata = dict(getattr(parsed, "metadata", {}) or {})
                parsed_metadata.update({key: value for key, value in metadata.items() if key not in parsed_metadata})
                return document_cls(
                    page_content=str(getattr(parsed, "page_content", "")).strip(),
                    metadata=parsed_metadata,
                )
            return document_cls(page_content=content.strip(), metadata=metadata)

        return document_cls(page_content=content.strip(), metadata=metadata)

    def _split_documents(self, documents: list[Any]) -> list[Any]:
        if not documents:
            return []
        if self._langchain_available():
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            semantic_chunks = self._split_documents_semantically(documents)
            if semantic_chunks is not None:
                return semantic_chunks

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            )
            return splitter.split_documents(documents)
        return self._split_documents_locally(documents)

    def _split_documents_semantically(self, documents: list[Any]) -> list[Any] | None:
        if not self._semantic_chunking_enabled:
            return None
        try:
            from langchain_experimental.text_splitter import SemanticChunker
        except ImportError:
            return None
        try:
            splitter = SemanticChunker(
                embeddings=self._embedder,
                breakpoint_threshold_type="percentile",
            )
            return splitter.split_documents(documents)
        except Exception:
            return None

    def _ensure_langchain_dependencies(self) -> None:
        try:
            __import__("langchain_core.documents")
            __import__("langchain_text_splitters")
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError(
                "langchain_dependencies_missing: install langchain, langchain-core, and langchain-text-splitters"
            ) from exc

    def _langchain_available(self) -> bool:
        try:
            self._ensure_langchain_dependencies()
        except RuntimeError:
            return False
        return True

    def _document_class(self) -> Any:
        if self._langchain_available():
            from langchain_core.documents import Document

            return Document
        return _SimpleDocument

    def _split_documents_locally(self, documents: list[Any]) -> list[Any]:
        chunks: list[_SimpleDocument] = []
        overlap = self._chunk_overlap
        size = self._chunk_size
        for document in documents:
            text = str(getattr(document, "page_content", "")).strip()
            metadata = dict(getattr(document, "metadata", {}) or {})
            if not text:
                continue
            if len(text) <= size:
                chunks.append(_SimpleDocument(page_content=text, metadata=metadata))
                continue
            start = 0
            while start < len(text):
                end = min(len(text), start + size)
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append(_SimpleDocument(page_content=chunk_text, metadata=metadata))
                if end >= len(text):
                    break
                start = max(start + 1, end - overlap)
        return chunks

    def _resolve_source_path(self, *, project_root: Path, source_path: Path) -> Path:
        if source_path.is_absolute():
            return source_path
        candidate = project_root / source_path
        if candidate.exists():
            return candidate
        repo_root_candidate = project_root.parents[1] / source_path
        return repo_root_candidate

    def _snippet(self, text: str, *, limit: int = 240) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: max(1, limit - 3)].rstrip() + "..."

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return numerator / (left_norm * right_norm)
