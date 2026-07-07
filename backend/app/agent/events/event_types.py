"""Event layer: strongly-typed stream events used by ReplayBuffer and SSE API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.protocol.messages import IntentType, RouteSummaryDto


STREAM_EVENT_NAMES = (
    "session.started",
    "subagent.changed",
    "worker.started",
    "worker.completed",
    "worker.failed",
    "assistant.token",
    "tool.started",
    "tool.progress",
    "tool.completed",
    "tool.failed",
    "navigation.route_ready",
    "assistant.completed",
    "session.failed",
)

EventName = Literal[*STREAM_EVENT_NAMES]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StreamEventData(BaseModel):
    """Base class for typed SSE event payloads.

    Event payloads are intentionally forward-compatible: producers and clients
    may add fields, while required fields remain contract-tested.
    """

    model_config = ConfigDict(extra="allow")


class SessionStartedData(StreamEventData):
    intent: IntentType
    active_subagent: str
    model: str | None = None


class SubagentChangedData(StreamEventData):
    active_subagent: str
    to_subagent: str
    reason: str | None = None
    from_subagent: str | None = None
    worker_run_id: str | None = None


class WorkerStartedData(StreamEventData):
    worker: str
    run_id: str
    active_subagent: str
    task_preview: str | None = None


class WorkerCompletedData(StreamEventData):
    worker: str
    run_id: str
    active_subagent: str
    status: str | None = None
    summary: str | None = None


class WorkerFailedData(StreamEventData):
    worker: str
    run_id: str
    error: str
    active_subagent: str


class AssistantTokenData(StreamEventData):
    delta: str
    content: str
    index: int
    total: int
    active_subagent: str
    text_preview: str | None = None


class ToolEventData(StreamEventData):
    tool: str
    call_id: str
    active_subagent: str
    worker_run_id: str | None = None


class ToolProgressData(ToolEventData):
    message: str | None = None
    progress: float | None = None


class ToolCompletedData(ToolEventData):
    distance_m: int | None = None


class ToolFailedData(ToolEventData):
    error: str


class NavigationRouteReadyData(RouteSummaryDto):
    model_config = ConfigDict(extra="allow")


class AssistantCompletedData(StreamEventData):
    reply: str
    active_subagent: str


class SessionFailedData(StreamEventData):
    error: str
    active_subagent: str


EVENT_DATA_MODELS: dict[EventName, type[BaseModel]] = {
    "session.started": SessionStartedData,
    "subagent.changed": SubagentChangedData,
    "worker.started": WorkerStartedData,
    "worker.completed": WorkerCompletedData,
    "worker.failed": WorkerFailedData,
    "assistant.token": AssistantTokenData,
    "tool.started": ToolEventData,
    "tool.progress": ToolProgressData,
    "tool.completed": ToolCompletedData,
    "tool.failed": ToolFailedData,
    "navigation.route_ready": NavigationRouteReadyData,
    "assistant.completed": AssistantCompletedData,
    "session.failed": SessionFailedData,
}


class StreamEvent(BaseModel):
    """Single stream event persisted in memory for SSE replay."""

    id: int
    session_id: str
    event: EventName
    at: str = Field(default_factory=utc_now_iso)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_data_contract(self) -> "StreamEvent":
        data_model = EVENT_DATA_MODELS[self.event]
        self.data = data_model.model_validate(self.data).model_dump(mode="json")
        return self
