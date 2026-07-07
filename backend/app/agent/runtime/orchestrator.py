"""Compatibility entrypoint: delegate chat execution to ReAct runtime.
兼容性入口点：将聊天执行委托给ReAct运行时。
"""

from __future__ import annotations

import asyncio
from threading import Lock
from uuid import uuid4

from app.infra.observability.logger import get_logger
from app.agent.runtime.react_runtime import ReactRuntime
from app.agent.runtime.session_state import (
    SessionOwnershipError,
    SessionRunConflictError,
    SessionRunReservation,
    SessionStateStore,
)
from app.protocol.messages import ChatRequest, ChatResponse


logger = get_logger(__name__)


class SessionAlreadyRunningError(RuntimeError):
    """Raised when the same chat session is dispatched concurrently."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session '{session_id}' is already running")
        self.session_id = session_id


class Orchestrator:
    """Backward-compatible orchestrator facade."""

    def __init__(self, *, react_runtime: ReactRuntime, session_store: SessionStateStore) -> None:
        self._react_runtime = react_runtime
        self._session_store = session_store
        self._lock = Lock()
        self._active_sessions: set[str] = set()
        self._background_tasks: dict[str, asyncio.Task[None]] = {}

    async def run_chat(self, request: ChatRequest) -> ChatResponse:
        """Run chat synchronously in the current thread, blocking until completion.
        运行聊天在当前线程中同步执行，直到完成才返回。"""
        normalized = self._normalize_request(request)
        reservation = self._reserve_session(normalized)
        if not reservation.started:
            raise SessionAlreadyRunningError(normalized.session_id or reservation.session_id)
        run_status = "completed"
        try:
            return await self._react_runtime.run_chat(normalized)
        except Exception:
            run_status = "failed"
            raise
        finally:
            if normalized.session_id:
                self._session_store.finish_run(normalized.session_id, status=run_status)
            self._release_session(normalized.session_id)

    async def dispatch_chat(self, request: ChatRequest) -> SessionRunReservation:
        """Dispatch chat to run in a background task, returning immediately.
        分派聊天在后台任务中执行，并立即返回。"""
        normalized = self._normalize_request(request)
        reservation = self._reserve_session(normalized)
        if not reservation.started:
            return reservation
        try:
            task = asyncio.create_task(
                self._run_chat_in_background(normalized),
                name=f"chat-run-{normalized.session_id}",
            )
            with self._lock:
                self._background_tasks[normalized.session_id] = task
            return reservation
        except Exception:
            self._release_session(normalized.session_id)
            if normalized.session_id:
                self._session_store.finish_run(normalized.session_id, status="failed")
            raise

    def is_session_running(self, session_id: str) -> bool:
        snapshot = self._session_store.snapshot(session_id)
        if snapshot is not None and snapshot.run_status == "running":
            return True
        with self._lock:
            return session_id in self._active_sessions

    async def _run_chat_in_background(self, request: ChatRequest) -> None:
        """Internal method to run chat in a background task, with error handling and session cleanup.
        在后台任务中运行聊天的内部方法，包含错误处理和会话清理"""
        session_id = request.session_id
        run_status = "completed"
        try:
            await self._react_runtime.run_chat(request)
        except Exception:
            run_status = "failed"
            logger.exception("chat.background.failed session_id=%s", session_id)
        finally:
            if session_id:
                self._session_store.finish_run(session_id, status=run_status)
            self._release_session(session_id)
            with self._lock:
                if session_id:
                    self._background_tasks.pop(session_id, None)

    def _normalize_request(self, request: ChatRequest) -> ChatRequest:
        if request.session_id:
            return request
        return request.model_copy(update={"session_id": f"s_{uuid4().hex[:12]}"})

    def _reserve_session(self, request: ChatRequest) -> SessionRunReservation:
        session_id = request.session_id
        if not session_id:
            raise ValueError("session_id is required before dispatching chat")
        try:
            reservation = self._session_store.reserve_run(
                session_id,
                client_id=request.client_id,
                idempotency_key=request.idempotency_key,
            )
        except SessionRunConflictError as exc:
            raise SessionAlreadyRunningError(exc.session_id) from exc
        if not reservation.started:
            return reservation
        with self._lock:
            if session_id in self._active_sessions:
                self._session_store.finish_run(session_id, status="failed")
                raise SessionAlreadyRunningError(session_id)
            self._active_sessions.add(session_id)
        self._react_runtime.prepare_session(session_id, client_id=request.client_id)
        return reservation

    def _release_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._active_sessions.discard(session_id)
