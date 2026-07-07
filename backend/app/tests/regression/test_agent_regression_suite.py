"""Regression and failure-drill tests for the Agent execution contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.events.replay_buffer import ReplayBuffer
from app.agent.runtime.react_runtime import ReactRuntime, _infer_intent
from app.agent.runtime.session_state import AgentSessionState
from app.agent.tools.builtin.query_rewrite import rewrite_query
from app.agent.tools.registry import ToolExecutionResult
from app.protocol.messages import ChatRequest


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _runtime() -> ReactRuntime:
    return object.__new__(ReactRuntime)


def _golden_questions() -> list[dict[str, object]]:
    return json.loads((FIXTURE_DIR / "agent_golden_questions.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _golden_questions(), ids=lambda item: str(item["id"]))
def test_agent_golden_questions_keep_intent_and_query_rewrite_stable(case: dict[str, object]) -> None:
    question = str(case["question"])
    rewritten = rewrite_query(question)
    rewritten_payload = rewritten.to_memory_payload()

    assert _infer_intent(question) == case["expected_intent"]
    for key, expected in dict(case["expected_query"]).items():
        assert rewritten_payload.get(key) == expected


def test_tool_failure_drill_records_trace_and_falls_back_gracefully() -> None:
    runtime = _runtime()
    state = AgentSessionState(session_id="s_failure_drill")
    state.intent = "search"
    state.working_memory = runtime._prepare_turn_memory(state.working_memory)

    runtime._apply_tool_memory(
        state=state,
        result=ToolExecutionResult(
            call_id="call_db_down",
            tool_name="db_query_tool",
            status="failed",
            output={"error": {"message": "database timeout"}},
            error_message="database timeout",
            trace_id="trace-1",
            tool_trace_id="tool-trace-1",
            attempt_count=2,
            duration_ms=1510.0,
            governance={"policy": {"timeout_seconds": 1.0}},
        ),
    )

    fallback = runtime._fallback_reply(state, ChatRequest(message="帮我找 Gamma Arcade"))

    assert "工具执行失败" in fallback
    assert "database timeout" in fallback
    assert state.working_memory["last_error"] == {"message": "database timeout"}
    assert state.working_memory["tool_trace"][0]["tool"] == "db_query_tool"
    assert state.working_memory["tool_trace"][0]["status"] == "failed"
    assert state.working_memory["tool_trace"][0]["attempt_count"] == 2


def test_sse_replay_drill_preserves_stage_order_and_resumes_after_offset() -> None:
    replay_buffer = ReplayBuffer(max_events_per_session=20)
    session_id = "s_replay_drill"

    events = [
        replay_buffer.append(session_id, "session.started", {"intent": "navigate", "active_subagent": "main_agent"}),
        replay_buffer.append(
            session_id,
            "subagent.changed",
            {
                "active_subagent": "navigation_worker",
                "to_subagent": "navigation_worker",
                "from_subagent": "main_agent",
            },
        ),
        replay_buffer.append(
            session_id,
            "tool.started",
            {"tool": "route_plan_tool", "call_id": "call_route", "active_subagent": "navigation_worker"},
        ),
        replay_buffer.append(
            session_id,
            "navigation.route_ready",
            {
                "schema_version": 1,
                "provider": "amap",
                "mode": "walking",
                "polyline": [{"lng": 121.4, "lat": 31.2}, {"lng": 121.5, "lat": 31.3}],
                "active_subagent": "navigation_worker",
            },
        ),
        replay_buffer.append(
            session_id,
            "assistant.completed",
            {"reply": "路线已生成", "active_subagent": "main_agent"},
        ),
    ]

    assert [event.event for event in events] == [
        "session.started",
        "subagent.changed",
        "tool.started",
        "navigation.route_ready",
        "assistant.completed",
    ]
    assert [event.id for event in events] == sorted(event.id for event in events)
    assert replay_buffer.list_events(session_id, last_event_id=events[1].id) == events[2:]
    assert events[3].data["schema_version"] == 1
