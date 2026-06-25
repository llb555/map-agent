"""LangChain-backed lightweight RAG service for knowledge retrieval."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any
import hashlib
import re
from collections import Counter

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
            self._model = SentenceTransformer(self._model_name)
        except Exception:
            self._model = SentenceTransformer(self._model_name, local_files_only=True)

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
        self._top_k = max(1, int(settings.rag_top_k))
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
        self._bm25_index: BM25Index | None = BM25Index() if self._hybrid_search_enabled else None

        self._lock = Lock()
        self._index_ready = False
        self._chunk_records: list[_ChunkRecord] = []
        self._load_error: str | None = None

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "source_path": str(self._source_path),
            "embeddings_configured": self._embedder.enabled,
            "reranker_enabled": self._reranker_enabled,
            "reranker_configured": self._reranker is not None and self._reranker.enabled,
            "hybrid_search_enabled": self._hybrid_search_enabled,
            "bm25_configured": self._bm25_index is not None,
            "index_ready": self._index_ready,
            "chunk_count": len(self._chunk_records),
            "load_error": self._load_error,
        }

    def _hybrid_search(
        self, *, query: str, query_embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        """Combine vector and BM25 scores using weighted fusion."""
        if not self._chunk_records or not self._bm25_index:
            return []

        # Vector search scores
        vector_scores = {
            idx: self._cosine_similarity(query_embedding, row.embedding)
            for idx, row in enumerate(self._chunk_records)
        }

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
        payload = {
            "backend": "langchain_memory",
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
            scored = [
                (self._cosine_similarity(query_embedding, row.embedding), row)
                for row in self._chunk_records
            ]
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
                for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:retrieval_limit]
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
        return payload

    def _ensure_index_loaded(self) -> None:
        if self._index_ready:
            return
        with self._lock:
            if self._index_ready:
                return
            documents = self._load_documents()
            chunks = self._split_documents(documents)
            if not chunks:
                self._chunk_records = []
                self._index_ready = True
                self._load_error = None
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

            # Build BM25 index if hybrid search is enabled
            if self._hybrid_search_enabled and self._bm25_index is not None and records:
                doc_texts = [record.text for record in records]
                self._bm25_index.build(doc_texts)

            self._index_ready = True
            self._load_error = None

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
                if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json", ".jsonl"}
            )

        documents: list[Any] = []
        for path in paths:
            suffix = path.suffix.lower()
            if suffix in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                documents.append(
                    document_cls(
                        page_content=text,
                        metadata={
                            "title": path.stem,
                            "source_uri": str(path),
                            "source_type": suffix.lstrip("."),
                        },
                    )
                )
                continue

            if suffix == ".jsonl":
                documents.extend(self._documents_from_jsonl(path=path, document_cls=document_cls))
                continue

            documents.extend(self._documents_from_json(path=path, document_cls=document_cls))
        return documents

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
        return document_cls(page_content=content.strip(), metadata=metadata)

    def _split_documents(self, documents: list[Any]) -> list[Any]:
        if not documents:
            return []
        if self._langchain_available():
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            )
            return splitter.split_documents(documents)
        return self._split_documents_locally(documents)

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
