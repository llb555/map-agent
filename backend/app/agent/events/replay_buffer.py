"""Event layer: bounded replay buffer for per-session SSE reconnect."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import json
from pathlib import Path
from threading import Lock
from typing import Iterator

from app.agent.events.event_types import EventName, StreamEvent
from app.agent.runtime.session_state import SessionStateStore


class ReplayBuffer:
    """Keep recent events by session_id and support replay from last_event_id.

    Events are mirrored to a JSONL log when storage_path is configured. That
    lets a restarted worker replay already-emitted terminal events instead of
    dropping the browser on reconnect.
    """

    def __init__(
        self,
        max_events_per_session: int = 200,
        session_store: SessionStateStore | None = None,
        storage_path: Path | None = None,
    ) -> None:
        self._max_events_per_session = max(10, max_events_per_session)
        self._sessions: dict[str, deque[StreamEvent]] = {}
        self._seq = 0
        self._lock = Lock()
        self._session_store = session_store
        self._storage_path = storage_path
        self._load_from_disk()

    def bind_session_store(self, session_store: SessionStateStore) -> None:
        self._session_store = session_store

    def append(self, session_id: str, event_name: EventName, data: dict | None = None) -> StreamEvent:
        """Append a stream event and return it."""
        with self._lock:
            if self._storage_path is None:
                self._seq += 1
                event = self._make_event(session_id, event_name, data)
                self._remember_event_locked(event)
                return event

            with self._file_lock():
                self._seq = max(self._seq, self._max_event_id_from_disk_unlocked())
                self._seq += 1
                event = self._make_event(session_id, event_name, data)
                self._remember_event_locked(event)
                self._append_to_disk_unlocked(event)
                return event

    def _make_event(self, session_id: str, event_name: EventName, data: dict | None) -> StreamEvent:
        return StreamEvent(
            id=self._seq,
            session_id=session_id,
            event=event_name,
            data=data or {},
        )

    def _remember_event_locked(self, event: StreamEvent) -> None:
        bucket = self._sessions.setdefault(event.session_id, deque(maxlen=self._max_events_per_session))
        bucket.append(event)
        if self._session_store is not None:
            self._session_store.record_stream_offset(event.session_id, event.id)

    def reset(self, session_id: str) -> None:
        """Drop buffered events for one session before a fresh execution starts."""
        with self._lock:
            self._sessions.pop(session_id, None)
            self._drop_session_from_disk_locked(session_id)

    def list_events(self, session_id: str, last_event_id: int | None = None) -> list[StreamEvent]:
        """List buffered events newer than last_event_id."""
        with self._lock:
            bucket = self._sessions.get(session_id)
            if not bucket:
                return []
            if last_event_id is None:
                return list(bucket)
            return [item for item in bucket if item.id > last_event_id]

    def _load_from_disk(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        sessions: dict[str, deque[StreamEvent]] = {}
        seq = 0
        try:
            with self._file_lock():
                for line in self._storage_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        event = StreamEvent.model_validate(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
                    seq = max(seq, event.id)
                    bucket = sessions.setdefault(
                        event.session_id,
                        deque(maxlen=self._max_events_per_session),
                    )
                    bucket.append(event)
        except OSError:
            return
        self._sessions = sessions
        self._seq = seq

    def _append_to_disk_unlocked(self, event: StreamEvent) -> None:
        if self._storage_path is None:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self._storage_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
                handle.write("\n")
        except OSError:
            return

    def _max_event_id_from_disk_unlocked(self) -> int:
        if self._storage_path is None or not self._storage_path.exists():
            return 0
        max_id = 0
        try:
            for line in self._storage_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_id = raw.get("id") if isinstance(raw, dict) else None
                if isinstance(event_id, int):
                    max_id = max(max_id, event_id)
        except OSError:
            return max_id
        return max_id

    def _drop_session_from_disk_locked(self, session_id: str) -> None:
        if self._storage_path is None:
            return
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._storage_path.with_name(f"{self._storage_path.name}.tmp")
            with self._file_lock():
                events: list[StreamEvent] = []
                if self._storage_path.exists():
                    for line in self._storage_path.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        try:
                            event = StreamEvent.model_validate(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if event.session_id != session_id:
                            events.append(event)
                temp_path.write_text(
                    "".join(
                        json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                temp_path.replace(self._storage_path)
        except OSError:
            return

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
