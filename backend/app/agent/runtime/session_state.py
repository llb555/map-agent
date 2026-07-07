"""Session state store for multi-turn ReAct execution."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, Literal

TurnRole = Literal["user", "assistant", "tool"]
TurnScope = Literal["conversation", "worker"]
SessionStatus = Literal["idle", "running", "completed", "failed"]
RunStatus = Literal["idle", "running", "completed", "failed"]
logger = logging.getLogger(__name__)


class SessionOwnershipError(RuntimeError):
    """Raised when a request tries to mutate a session owned by another client."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session '{session_id}' is not available for this client")
        self.session_id = session_id


class SessionRunConflictError(RuntimeError):
    """Raised when a new run conflicts with a persisted in-flight run."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session '{session_id}' is already running")
        self.session_id = session_id


@dataclass(frozen=True)
class SessionRunReservation:
    """Result of reserving a session run."""

    session_id: str
    started: bool
    idempotency_key: str | None
    last_stream_offset: int


def _utc_now_iso() -> str:
    """Generate UTC ISO8601 timestamp used by chat session snapshots."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class AgentTurn:
    """One persisted turn item for model context reconstruction."""

    role: TurnRole
    content: str
    agent: str | None = None
    name: str | None = None
    call_id: str | None = None
    worker_run_id: str | None = None
    scope: TurnScope = "conversation"
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class AgentSessionState:
    """Session-level execution state and memory."""

    session_id: str
    client_id: str | None = None
    turn_index: int = 0
    active_subagent: str = "main_agent"
    intent: str = "search"
    status: SessionStatus = "idle"
    run_status: RunStatus = "idle"
    idempotency_key: str | None = None
    current_run_id: str | None = None
    last_stream_offset: int = 0
    last_error: str | None = None
    turns: list[AgentTurn] = field(default_factory=list)
    working_memory: dict[str, Any] = field(default_factory=dict)
    previous_response_id: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)


def ensure_working_memory_shape(memory: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize working memory into the phase-1 hub layout. 
    This allows flexible schema evolution while ensuring the expected sub-keys exist for easier access."""
    normalized = memory if isinstance(memory, dict) else {}
    artifacts = normalized.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    normalized["artifacts"] = artifacts

    worker_runs = normalized.get("worker_runs")
    if not isinstance(worker_runs, list):
        worker_runs = []
    normalized["worker_runs"] = [item for item in worker_runs if isinstance(item, dict)]
    return normalized


def get_working_memory_artifact(memory: dict[str, Any] | None, key: str) -> Any:
    normalized = ensure_working_memory_shape(memory)
    artifacts = normalized["artifacts"]
    if key in artifacts:
        return artifacts.get(key)
    return normalized.get(key)


def set_working_memory_artifact(memory: dict[str, Any] | None, key: str, value: Any) -> None:
    normalized = ensure_working_memory_shape(memory)
    normalized["artifacts"][key] = deepcopy(value)


def append_worker_run(memory: dict[str, Any] | None, run: dict[str, Any], *, max_entries: int = 20) -> None:
    normalized = ensure_working_memory_shape(memory)
    worker_runs = normalized["worker_runs"]
    worker_runs.append(deepcopy(run))
    if len(worker_runs) > max_entries:
        del worker_runs[:-max_entries]


class SessionStateStore:
    """Thread-safe session store keyed by session_id with optional disk persistence."""

    def __init__(self, *, storage_path: Path | None = None, flush_interval_seconds: float = 0.5) -> None:
        self._lock = Lock()
        self._states: dict[str, AgentSessionState] = {}
        self._storage_path = storage_path
        self._flush_interval_seconds = max(0.0, float(flush_interval_seconds))
        self._last_flush_at = 0.0
        self._load_from_disk()

    def get_or_create(self, session_id: str) -> AgentSessionState:
        with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = AgentSessionState(session_id=session_id)
                self._states[session_id] = state
            return deepcopy(state)

    def snapshot(self, session_id: str, *, client_id: str | None = None) -> AgentSessionState | None:
        """Return deep-copied session state for API serialization."""
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
            state = self._states.get(session_id)
            if state is None:
                return None
            if not _client_can_access(state, client_id):
                return None
            return deepcopy(state)

    def list_snapshots(self, *, limit: int = 50, client_id: str | None = None) -> list[AgentSessionState]:
        """Return recent session snapshots sorted by updated_at desc."""
        safe_limit = max(1, min(limit, 200))
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
            snapshots = [
                deepcopy(item)
                for item in self._states.values()
                if _client_matches_list_scope(item, client_id)
            ]
        snapshots.sort(key=lambda item: item.updated_at, reverse=True)
        return snapshots[:safe_limit]

    def delete(self, session_id: str, *, client_id: str | None = None) -> bool:
        """Delete one session by id; return True when it existed."""
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
                state = self._states.get(session_id)
                existed = state is not None and _client_can_access(state, client_id)
                if existed:
                    del self._states[session_id]
                    self._flush_to_disk_locked()
                return existed

    def reserve_run(
        self,
        session_id: str,
        *,
        client_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SessionRunReservation:
        """Atomically reserve a new run, or return the existing idempotent run."""
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
                return self._reserve_run_locked(
                    session_id,
                    client_id=client_id,
                    idempotency_key=idempotency_key,
                )

    def _reserve_run_locked(
        self,
        session_id: str,
        *,
        client_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> SessionRunReservation:
        state = self._states.get(session_id)
        if state is None:
            state = AgentSessionState(session_id=session_id)
            self._states[session_id] = state
        if not _client_can_access(state, client_id):
            raise SessionOwnershipError(session_id)

        incoming_key = _normalize_idempotency_key(idempotency_key)
        existing_key = _normalize_idempotency_key(state.idempotency_key)
        is_same_run = bool(incoming_key and existing_key and incoming_key == existing_key)
        if state.run_status == "running" or state.status == "running":
            if is_same_run:
                return SessionRunReservation(
                    session_id=session_id,
                    started=False,
                    idempotency_key=existing_key,
                    last_stream_offset=state.last_stream_offset,
                )
            raise SessionRunConflictError(session_id)
        if is_same_run and state.run_status in {"completed", "failed"}:
            return SessionRunReservation(
                session_id=session_id,
                started=False,
                idempotency_key=existing_key,
                last_stream_offset=state.last_stream_offset,
            )

        state.client_id = state.client_id or client_id
        state.status = "running"
        state.run_status = "running"
        state.idempotency_key = incoming_key
        state.current_run_id = incoming_key
        state.last_error = None
        state.updated_at = _utc_now_iso()
        state.working_memory = ensure_working_memory_shape(state.working_memory)
        self._states[session_id] = deepcopy(state)
        self._flush_to_disk_locked()
        self._last_flush_at = time.monotonic()
        return SessionRunReservation(
            session_id=session_id,
            started=True,
            idempotency_key=incoming_key,
            last_stream_offset=state.last_stream_offset,
        )

    def finish_run(self, session_id: str, *, status: RunStatus) -> None:
        """Persist terminal run state after a background task exits."""
        if status not in {"completed", "failed"}:
            return
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
                self._finish_run_locked(session_id, status=status)

    def _finish_run_locked(self, session_id: str, *, status: RunStatus) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        state.run_status = status
        state.updated_at = _utc_now_iso()
        self._states[session_id] = deepcopy(state)
        self._flush_to_disk_locked()
        self._last_flush_at = time.monotonic()

    def record_stream_offset(self, session_id: str, offset: int) -> None:
        """Persist the latest SSE offset observed for a session."""
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
                self._record_stream_offset_locked(session_id, offset)

    def _record_stream_offset_locked(self, session_id: str, offset: int) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        if offset <= state.last_stream_offset:
            return
        state.last_stream_offset = offset
        state.updated_at = _utc_now_iso()
        self._states[session_id] = deepcopy(state)
        self._flush_to_disk_locked()
        self._last_flush_at = time.monotonic()

    def save(self, state: AgentSessionState, *, force_flush: bool = False) -> None:
        """Persist one mutated session state and flush the snapshot file."""
        with self._lock:
            with self._file_lock():
                self._load_from_disk_locked()
                self._save_locked(state, force_flush=force_flush)

    def _save_locked(self, state: AgentSessionState, *, force_flush: bool = False) -> None:
        self._states[state.session_id] = deepcopy(state)
        self._flush_to_disk_locked()
        self._last_flush_at = time.monotonic()

    def flush(self) -> None:
        with self._lock:
            with self._file_lock():
                self._flush_to_disk_locked()
                self._last_flush_at = time.monotonic()

    def _load_from_disk(self) -> None:
        with self._file_lock():
            self._load_from_disk_locked()

    def _load_from_disk_locked(self) -> None:
        if self._storage_path is None:
            return
        if self._storage_path.is_dir():
            self._load_from_session_directory(self._storage_path)
            return
        if not self._storage_path.exists():
            session_dir = self._session_directory_path()
            if session_dir.exists():
                self._load_from_session_directory(session_dir)
            return
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("session_store.load_failed path=%s error=%s", self._storage_path, exc)
            return

        raw_sessions = payload.get("sessions") if isinstance(payload, dict) else payload
        if not isinstance(raw_sessions, list):
            logger.warning("session_store.load_invalid path=%s", self._storage_path)
            return

        restored: dict[str, AgentSessionState] = {}
        for raw_state in raw_sessions:
            state = _state_from_dict(raw_state)
            if state is not None:
                restored[state.session_id] = state
        self._states = restored

    def _load_from_session_directory(self, directory: Path) -> None:
        restored: dict[str, AgentSessionState] = {}
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            state = _state_from_dict(payload)
            if state is not None:
                restored[state.session_id] = state
        self._states = restored

    def _flush_to_disk_locked(self) -> None:
        if self._storage_path is None: #if no storage path, skip disk flush
            return
        session_dir = self._session_directory_path()
        session_dir.mkdir(parents=True, exist_ok=True)
        existing_files = {path.stem for path in session_dir.glob("*.json")}
        active_ids = set(self._states.keys())

        for state in self._states.values():
            target_path = session_dir / f"{state.session_id}.json"
            temp_path = target_path.with_name(f"{target_path.name}.tmp")
            temp_path.write_text(
                json.dumps(_state_to_dict(state), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(target_path)

        for stale_id in existing_files - active_ids:
            stale_path = session_dir / f"{stale_id}.json"
            try:
                stale_path.unlink()
            except OSError:
                continue

        if self._storage_path.exists() and self._storage_path.is_file():
            try:
                self._storage_path.unlink()
            except OSError:
                pass

    def _should_flush_locked(self, state: AgentSessionState) -> bool:
        if self._storage_path is None:
            return False
        if state.status in {"completed", "failed"}:
            return True
        if self._last_flush_at <= 0:
            return False
        return (time.monotonic() - self._last_flush_at) >= self._flush_interval_seconds

    def _session_directory_path(self) -> Path:
        if self._storage_path is None:
            raise RuntimeError("session_storage_unavailable")
        if self._storage_path.suffix:
            return self._storage_path.with_suffix("")
        return self._storage_path

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        if self._storage_path is None:
            yield
            return
        lock_path = self._storage_path.with_name(f"{self._storage_path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                import fcntl
            except ImportError:  # pragma: no cover - Windows fallback
                yield
                return
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass


def _state_to_dict(state: AgentSessionState) -> dict[str, Any]:
    return {
        "session_id": state.session_id,
        "client_id": state.client_id,
        "turn_index": state.turn_index,
        "active_subagent": state.active_subagent,
        "intent": state.intent,
        "status": state.status,
        "run_status": state.run_status,
        "idempotency_key": state.idempotency_key,
        "current_run_id": state.current_run_id,
        "last_stream_offset": state.last_stream_offset,
        "last_error": state.last_error,
        "turns": [
            {
                "role": turn.role,
                "content": turn.content,
                "agent": turn.agent,
                "name": turn.name,
                "call_id": turn.call_id,
                "worker_run_id": turn.worker_run_id,
                "scope": turn.scope,
                "payload": turn.payload,
                "created_at": turn.created_at,
            }
            for turn in state.turns
        ],
        "working_memory": ensure_working_memory_shape(state.working_memory),
        "previous_response_id": state.previous_response_id,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def _state_from_dict(raw: object) -> AgentSessionState | None:
    if not isinstance(raw, dict):
        return None
    session_id = raw.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    turns_raw = raw.get("turns")
    turns: list[AgentTurn] = []
    if isinstance(turns_raw, list):
        for item in turns_raw:
            turn = _turn_from_dict(item)
            if turn is not None:
                turns.append(turn)
    working_memory = ensure_working_memory_shape(raw.get("working_memory"))
    return AgentSessionState(
        session_id=session_id,
        client_id=raw.get("client_id") if isinstance(raw.get("client_id"), str) else None,
        turn_index=_coerce_int(raw.get("turn_index"), default=0),
        active_subagent=_coerce_active_agent(raw.get("active_subagent"), default="main_agent"),
        intent=_coerce_str(raw.get("intent"), default="search"),
        status=_coerce_status(raw.get("status"), default="completed" if turns else "idle"),
        run_status=_coerce_run_status(raw.get("run_status"), default=_coerce_run_status(raw.get("status"), default="idle")),
        idempotency_key=_normalize_idempotency_key(raw.get("idempotency_key")),
        current_run_id=_normalize_idempotency_key(raw.get("current_run_id")),
        last_stream_offset=_coerce_int(raw.get("last_stream_offset"), default=0),
        last_error=raw.get("last_error") if isinstance(raw.get("last_error"), str) else None,
        turns=turns,
        working_memory=working_memory,
        previous_response_id=raw.get("previous_response_id")
        if isinstance(raw.get("previous_response_id"), str)
        else None,
        created_at=_coerce_str(raw.get("created_at"), default=_utc_now_iso()),
        updated_at=_coerce_str(raw.get("updated_at"), default=_utc_now_iso()),
    )


def _turn_from_dict(raw: object) -> AgentTurn | None:
    if not isinstance(raw, dict):
        return None
    role = raw.get("role")
    content = raw.get("content")
    if role not in {"user", "assistant", "tool"} or not isinstance(content, str):
        return None
    payload = raw.get("payload")
    return AgentTurn(
        role=role,
        content=content,
        agent=raw.get("agent") if isinstance(raw.get("agent"), str) else None,
        name=raw.get("name") if isinstance(raw.get("name"), str) else None,
        call_id=raw.get("call_id") if isinstance(raw.get("call_id"), str) else None,
        worker_run_id=raw.get("worker_run_id") if isinstance(raw.get("worker_run_id"), str) else None,
        scope=raw.get("scope") if raw.get("scope") in {"conversation", "worker"} else "conversation",
        payload=payload if isinstance(payload, dict) else {},
        created_at=_coerce_str(raw.get("created_at"), default=_utc_now_iso()),
    )


def _coerce_int(raw: object, *, default: int) -> int:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return default
    return default


def _coerce_str(raw: object, *, default: str) -> str:
    if isinstance(raw, str) and raw:
        return raw
    return default


def _coerce_status(raw: object, *, default: SessionStatus) -> SessionStatus:
    if raw in {"idle", "running", "completed", "failed"}:
        return raw
    return default


def _coerce_run_status(raw: object, *, default: RunStatus) -> RunStatus:
    if raw in {"idle", "running", "completed", "failed"}:
        return raw
    return default


def _normalize_idempotency_key(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    if not normalized:
        return None
    return normalized[:128]


def _coerce_active_agent(raw: object, *, default: str) -> str:
    if not isinstance(raw, str) or not raw:
        return default
    mapping = {
        "intent_router": "main_agent",
        "summary_agent": "main_agent",
        "search_agent": "search_worker",
        "navigation_agent": "navigation_worker",
    }
    return mapping.get(raw, raw)


def _client_can_access(state: AgentSessionState, client_id: str | None) -> bool:
    if client_id is None:
        return True
    return state.client_id in {None, client_id}


def _client_matches_list_scope(state: AgentSessionState, client_id: str | None) -> bool:
    if client_id is None:
        return True
    return state.client_id == client_id
