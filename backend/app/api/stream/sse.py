"""Stream API layer: SSE endpoint with replay support and heartbeat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_container, get_current_user
from app.auth.models import CurrentUser
from app.core.container import AppContainer

router = APIRouter(tags=["stream"])


def _format_sse(*, event: str, data: dict, event_id: int) -> str:
    body = json.dumps(data, ensure_ascii=False)
    return f"id: {event_id}\nevent: {event}\ndata: {body}\n\n"


@router.get("/api/stream/{session_id}")
async def stream(
    session_id: str,
    request: Request,
    client_id: str | None = Query(default=None, min_length=1, max_length=128),
    last_event_id: int | None = Query(default=None),
    last_event_id_header: str | None = Header(default=None, alias="Last-Event-ID"),
    container: AppContainer = Depends(get_container),
    user: CurrentUser | None = Depends(get_current_user),
) -> StreamingResponse:
    owner_scope = user.id if user is not None else client_id
    initial_snapshot = container.session_store.snapshot(session_id, client_id=owner_scope)
    if owner_scope is not None and (
        initial_snapshot is None or (user is not None and initial_snapshot.client_id != user.id)
    ):
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")

    async def iterator() -> AsyncIterator[str]:
        cursor = last_event_id
        if cursor is None and isinstance(last_event_id_header, str):
            try:
                cursor = int(last_event_id_header)
            except ValueError:
                cursor = None
        waited = 0
        while True:
            if await request.is_disconnected():
                return
            events = container.replay_buffer.list_events(session_id, cursor)
            if events:
                for evt in events:
                    cursor = evt.id
                    yield _format_sse(
                        event=evt.event,
                        data=evt.model_dump(mode="json"),
                        event_id=evt.id,
                    )
                    if evt.event in {"assistant.completed", "session.failed"}:
                        return
                waited = 0
            else:
                snapshot = container.session_store.snapshot(session_id, client_id=owner_scope)
                session_status = snapshot.status if snapshot is not None else None
                if session_status in {"completed", "failed"}:
                    return
                yield ": keep-alive\n\n"
                waited += 1
                if (
                    session_status not in {"running"}
                    and waited >= container.settings.sse_max_wait_seconds
                ):
                    return
            await asyncio.sleep(container.settings.sse_keepalive_seconds)

    return StreamingResponse(iterator(), media_type="text/event-stream")
