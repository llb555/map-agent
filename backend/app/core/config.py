"""Configuration layer: load runtime settings from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


_WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_absolute_path_like(path_like: str) -> bool:
    if _WINDOWS_ABS_PATH_RE.match(path_like):
        return True
    return Path(path_like).is_absolute()


def _resolve_path(path_like: str) -> Path:
    candidate = Path(path_like)
    if _is_absolute_path_like(path_like):
        return candidate
    if candidate.exists():
        return candidate
    project_root = Path(__file__).resolve().parents[3]
    rooted = project_root / candidate
    if rooted.exists():
        return rooted
    return candidate


def _resolve_project_path(path_like: str) -> Path:
    candidate = Path(path_like)
    if _is_absolute_path_like(path_like):
        return candidate
    project_root = Path(__file__).resolve().parents[3]
    return project_root / candidate


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv_if_exists() -> None:
    """加载项目根目录下的 .env 文件（如果存在），将其中的键值对设置到环境变量中，供后续配置加载使用。"""
    project_root = Path(__file__).resolve().parents[3]
    dotenv_path = project_root / ".env"
    if not dotenv_path.exists():
        return
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        parsed = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, parsed)


@dataclass(frozen=True)
class Settings:
    """Immutable application settings used across API/runtime layers."""

    app_name: str = "Arcadegent Agent API"
    app_version: str = "0.1.0"
    env: str = "dev"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    arcade_data_source: Literal["jsonl", "supabase"] = "jsonl"
    data_jsonl_path: Path = Path("data/local/arcades.jsonl")
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_timeout_seconds: float = 8.0
    chat_session_store_path: Path = Path("data/runtime/chat_sessions.json")
    chat_stream_event_store_path: Path = Path("data/runtime/chat_stream_events.jsonl")
    replay_buffer_size: int = 200
    sse_keepalive_seconds: float = 1.0
    sse_max_wait_seconds: int = 20
    enable_provider_fallback: bool = True
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 20.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 500
    vision_llm_api_key: str = ""
    vision_llm_base_url: str = ""
    vision_llm_model: str = ""
    vision_llm_timeout_seconds: float = 20.0
    vision_llm_temperature: float = 0.2
    vision_llm_max_tokens: int = 700
    rag_enabled: bool = False
    rag_source_path: Path = Path("data/local/knowledge")
    rag_chunk_size: int = 700
    rag_chunk_overlap: int = 120
    rag_semantic_chunking_enabled: bool = False
    rag_top_k: int = 4
    rag_embedding_api_key: str = ""
    rag_embedding_base_url: str = ""
    rag_embedding_model: str = ""
    rag_embedding_timeout_seconds: float = 20.0
    rag_vector_backend: Literal["memory", "faiss"] = "memory"
    rag_faiss_index_path: Path = Path("data/runtime/rag_index.faiss")
    rag_faiss_metadata_path: Path = Path("data/runtime/rag_index_meta.json")
    rag_reranker_enabled: bool = False
    rag_reranker_model: str = ""
    rag_reranker_top_k_multiplier: int = 5
    rag_reranker_timeout_seconds: float = 20.0
    rag_hybrid_search_enabled: bool = False
    rag_hybrid_alpha: float = 0.5
    rag_query_cache_enabled: bool = True
    rag_query_cache_max_entries: int = 128
    rag_query_cache_ttl_seconds: float = 120.0
    rag_snapshot_path: Path = Path("data/runtime/rag_snapshot.json")
    agent_max_steps: int = 20
    agent_context_window: int = 24
    agent_nodes_definitions_dir: Path = Path("app/agent/nodes/definitions")
    agent_tool_policy_file: Path = Path("app/agent/nodes/profiles/tool_policies.yaml")
    agent_subagent_yaml_overlay_enabled: bool = True
    agent_provider_profiles_file: Path = Path("app/agent/nodes/profiles/provider_profiles.yaml")
    agent_provider_profile: str = "default"
    mcp_default_timeout_seconds: float = 10.0
    mcp_servers_dir: Path = Path("backend/app/agent/tools/mcp/servers")
    amap_api_key: str = ""
    amap_base_url: str = "https://restapi.amap.com"
    amap_timeout_seconds: float = 8.0
    arcade_geo_cache_path: Path = Path("data/runtime/arcade_geo_cache.json")
    arcade_geo_sync_limit: int = 8
    arcade_geo_max_workers: int = 4
    arcade_geo_request_timeout_seconds: float = 1.2
    arcade_geo_flush_interval_seconds: float = 0.5
    chat_session_flush_interval_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from process env with deterministic defaults."""
        _load_dotenv_if_exists()
        arcade_data_source = os.getenv("ARCADE_DATA_SOURCE", cls.arcade_data_source).strip().lower()
        if arcade_data_source not in {"jsonl", "supabase"}:
            raise ValueError(f"invalid_arcade_data_source:{arcade_data_source}")
        rag_vector_backend = os.getenv("RAG_VECTOR_BACKEND", cls.rag_vector_backend).strip().lower()
        if rag_vector_backend not in {"memory", "faiss"}:
            raise ValueError(f"invalid_rag_vector_backend:{rag_vector_backend}")
        return cls(
            app_name=os.getenv("APP_NAME", cls.app_name),
            app_version=os.getenv("APP_VERSION", cls.app_version),
            env=os.getenv("APP_ENV", cls.env),
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", str(cls.port))),
            cors_allow_origins=os.getenv("CORS_ALLOW_ORIGINS", cls.cors_allow_origins),
            arcade_data_source=arcade_data_source,  # type: ignore[arg-type]
            data_jsonl_path=_resolve_path(os.getenv("ARCADE_DATA_JSONL", str(cls.data_jsonl_path))),
            supabase_url=os.getenv("SUPABASE_URL", cls.supabase_url).strip(),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", cls.supabase_anon_key).strip(),
            supabase_service_role_key=os.getenv(
                "SUPABASE_SERVICE_ROLE_KEY", cls.supabase_service_role_key
            ).strip(),
            supabase_timeout_seconds=float(
                os.getenv("SUPABASE_TIMEOUT_SECONDS", str(cls.supabase_timeout_seconds))
            ),
            chat_session_store_path=_resolve_project_path(
                os.getenv("CHAT_SESSION_STORE_PATH", str(cls.chat_session_store_path))
            ),
            chat_stream_event_store_path=_resolve_project_path(
                os.getenv("CHAT_STREAM_EVENT_STORE_PATH", str(cls.chat_stream_event_store_path))
            ),
            replay_buffer_size=int(os.getenv("REPLAY_BUFFER_SIZE", str(cls.replay_buffer_size))),
            sse_keepalive_seconds=float(
                os.getenv("SSE_KEEPALIVE_SECONDS", str(cls.sse_keepalive_seconds))
            ),
            sse_max_wait_seconds=int(
                os.getenv("SSE_MAX_WAIT_SECONDS", str(cls.sse_max_wait_seconds))
            ),
            enable_provider_fallback=_env_bool(
                "ENABLE_PROVIDER_FALLBACK", cls.enable_provider_fallback
            ),
            llm_api_key=os.getenv("LLM_API_KEY", cls.llm_api_key),
            llm_base_url=os.getenv("LLM_BASE_URL", cls.llm_base_url),
            llm_model=os.getenv("LLM_MODEL", cls.llm_model),
            llm_timeout_seconds=float(
                os.getenv("LLM_TIMEOUT_SECONDS", str(cls.llm_timeout_seconds))
            ),
            llm_temperature=float(
                os.getenv("LLM_TEMPERATURE", str(cls.llm_temperature))
            ),
            llm_max_tokens=int(
                os.getenv("LLM_MAX_TOKENS", str(cls.llm_max_tokens))
            ),
            vision_llm_api_key=os.getenv("VISION_LLM_API_KEY", cls.vision_llm_api_key),
            vision_llm_base_url=os.getenv("VISION_LLM_BASE_URL", cls.vision_llm_base_url),
            vision_llm_model=os.getenv("VISION_LLM_MODEL", cls.vision_llm_model),
            vision_llm_timeout_seconds=float(
                os.getenv("VISION_LLM_TIMEOUT_SECONDS", str(cls.vision_llm_timeout_seconds))
            ),
            vision_llm_temperature=float(
                os.getenv("VISION_LLM_TEMPERATURE", str(cls.vision_llm_temperature))
            ),
            vision_llm_max_tokens=int(
                os.getenv("VISION_LLM_MAX_TOKENS", str(cls.vision_llm_max_tokens))
            ),
            rag_enabled=_env_bool("RAG_ENABLED", cls.rag_enabled),
            rag_source_path=_resolve_path(os.getenv("RAG_SOURCE_PATH", str(cls.rag_source_path))),
            rag_chunk_size=int(os.getenv("RAG_CHUNK_SIZE", str(cls.rag_chunk_size))),
            rag_chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", str(cls.rag_chunk_overlap))),
            rag_semantic_chunking_enabled=_env_bool(
                "RAG_SEMANTIC_CHUNKING_ENABLED",
                cls.rag_semantic_chunking_enabled,
            ),
            rag_top_k=int(os.getenv("RAG_TOP_K", str(cls.rag_top_k))),
            rag_embedding_api_key=os.getenv("RAG_EMBEDDING_API_KEY", cls.rag_embedding_api_key),
            rag_embedding_base_url=os.getenv("RAG_EMBEDDING_BASE_URL", cls.rag_embedding_base_url),
            rag_embedding_model=os.getenv("RAG_EMBEDDING_MODEL", cls.rag_embedding_model),
            rag_embedding_timeout_seconds=float(
                os.getenv(
                    "RAG_EMBEDDING_TIMEOUT_SECONDS",
                    str(cls.rag_embedding_timeout_seconds),
                )
            ),
            rag_vector_backend=rag_vector_backend,  # type: ignore[arg-type]
            rag_faiss_index_path=_resolve_project_path(
                os.getenv("RAG_FAISS_INDEX_PATH", str(cls.rag_faiss_index_path))
            ),
            rag_faiss_metadata_path=_resolve_project_path(
                os.getenv("RAG_FAISS_METADATA_PATH", str(cls.rag_faiss_metadata_path))
            ),
            rag_reranker_enabled=_env_bool("RAG_RERANKER_ENABLED", cls.rag_reranker_enabled),
            rag_reranker_model=os.getenv("RAG_RERANKER_MODEL", cls.rag_reranker_model),
            rag_reranker_top_k_multiplier=int(
                os.getenv("RAG_RERANKER_TOP_K_MULTIPLIER", str(cls.rag_reranker_top_k_multiplier))
            ),
            rag_reranker_timeout_seconds=float(
                os.getenv("RAG_RERANKER_TIMEOUT_SECONDS", str(cls.rag_reranker_timeout_seconds))
            ),
            rag_hybrid_search_enabled=_env_bool("RAG_HYBRID_SEARCH_ENABLED", cls.rag_hybrid_search_enabled),
            rag_hybrid_alpha=float(os.getenv("RAG_HYBRID_ALPHA", str(cls.rag_hybrid_alpha))),
            rag_query_cache_enabled=_env_bool("RAG_QUERY_CACHE_ENABLED", cls.rag_query_cache_enabled),
            rag_query_cache_max_entries=int(
                os.getenv("RAG_QUERY_CACHE_MAX_ENTRIES", str(cls.rag_query_cache_max_entries))
            ),
            rag_query_cache_ttl_seconds=float(
                os.getenv("RAG_QUERY_CACHE_TTL_SECONDS", str(cls.rag_query_cache_ttl_seconds))
            ),
            rag_snapshot_path=_resolve_project_path(
                os.getenv("RAG_SNAPSHOT_PATH", str(cls.rag_snapshot_path))
            ),
            agent_max_steps=int(
                os.getenv("AGENT_MAX_STEPS", str(cls.agent_max_steps))
            ),
            agent_context_window=int(
                os.getenv("AGENT_CONTEXT_WINDOW", str(cls.agent_context_window))
            ),
            agent_nodes_definitions_dir=_resolve_path(
                os.getenv(
                    "AGENT_NODES_DEFINITIONS_DIR",
                    str(cls.agent_nodes_definitions_dir),
                )
            ),
            agent_tool_policy_file=_resolve_path(
                os.getenv("AGENT_TOOL_POLICY_FILE", str(cls.agent_tool_policy_file))
            ),
            agent_subagent_yaml_overlay_enabled=_env_bool(
                "AGENT_SUBAGENT_YAML_OVERLAY_ENABLED",
                cls.agent_subagent_yaml_overlay_enabled,
            ),
            agent_provider_profiles_file=_resolve_path(
                os.getenv(
                    "AGENT_PROVIDER_PROFILES_FILE",
                    str(cls.agent_provider_profiles_file),
                )
            ),
            agent_provider_profile=os.getenv(
                "AGENT_PROVIDER_PROFILE",
                cls.agent_provider_profile,
            ),
            mcp_default_timeout_seconds=float(
                os.getenv("MCP_DEFAULT_TIMEOUT_SECONDS", str(cls.mcp_default_timeout_seconds))
            ),
            mcp_servers_dir=_resolve_path(
                os.getenv("MCP_SERVERS_DIR", str(cls.mcp_servers_dir))
            ),
            amap_api_key=os.getenv("AMAP_API_KEY", cls.amap_api_key),
            amap_base_url=os.getenv("AMAP_BASE_URL", cls.amap_base_url),
            amap_timeout_seconds=float(
                os.getenv("AMAP_TIMEOUT_SECONDS", str(cls.amap_timeout_seconds))
            ),
            arcade_geo_cache_path=_resolve_project_path(
                os.getenv("ARCADE_GEO_CACHE_PATH", str(cls.arcade_geo_cache_path))
            ),
            arcade_geo_sync_limit=int(
                os.getenv("ARCADE_GEO_SYNC_LIMIT", str(cls.arcade_geo_sync_limit))
            ),
            arcade_geo_max_workers=int(
                os.getenv("ARCADE_GEO_MAX_WORKERS", str(cls.arcade_geo_max_workers))
            ),
            arcade_geo_request_timeout_seconds=float(
                os.getenv(
                    "ARCADE_GEO_REQUEST_TIMEOUT_SECONDS",
                    str(cls.arcade_geo_request_timeout_seconds),
                )
            ),
            arcade_geo_flush_interval_seconds=float(
                os.getenv(
                    "ARCADE_GEO_FLUSH_INTERVAL_SECONDS",
                    str(cls.arcade_geo_flush_interval_seconds),
                )
            ),
            chat_session_flush_interval_seconds=float(
                os.getenv(
                    "CHAT_SESSION_FLUSH_INTERVAL_SECONDS",
                    str(cls.chat_session_flush_interval_seconds),
                )
            ),
        )
