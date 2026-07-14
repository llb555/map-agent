"""Keyless demo-mode coverage across data, map payloads, and SSE events."""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.core.container import build_container
from app.protocol.messages import ChatRequest, ClientLocationContext


def _container(tmp_path):
    (tmp_path / "mcp").mkdir(exist_ok=True)
    return build_container(Settings(
        demo_mode=True,
        llm_api_key="",
        amap_api_key="",
        chat_session_store_path=tmp_path / "sessions.json",
        chat_stream_event_store_path=tmp_path / "events.jsonl",
        arcade_geo_cache_path=tmp_path / "geo.json",
        knowledge_submission_store_path=tmp_path / "knowledge.json",
        knowledge_submission_files_path=tmp_path / "knowledge",
        mcp_servers_dir=tmp_path / "mcp",
        rag_enabled=False,
    ))


def test_demo_mode_has_sixty_searchable_arcades_and_health(tmp_path) -> None:
    container = _container(tmp_path)
    rows, total = container.store.list_shops(
        keyword=None, province_code=None, city_code=None, county_code=None,
        has_arcades=True, page=1, page_size=100,
    )
    assert total == 60
    assert len(rows) == 60
    assert container.store.health()["loaded_rows"] == 60


def test_demo_mode_keyless_chat_builds_map_and_sse_events(tmp_path) -> None:
    container = _container(tmp_path)
    request = ChatRequest(
        session_id="demo-search",
        message="帮我找上海的 maimai 机厅",
        location=ClientLocationContext(lng=121.50, lat=31.22, city="上海市"),
    )
    response = asyncio.run(container.orchestrator.run_chat(request))

    assert response.shops
    assert response.map_artifact is not None
    assert response.map_artifact.scene == "agent_candidates"
    assert "确定性本地搜索降级" in response.reply
    event_names = [event.event for event in container.replay_buffer.list_events("demo-search", None)]
    assert "tool.started" in event_names
    assert "assistant.token" in event_names
    assert event_names[-1] == "assistant.completed"


def test_demo_mode_navigation_exposes_offline_route_degradation(tmp_path) -> None:
    container = _container(tmp_path)
    response = asyncio.run(container.orchestrator.run_chat(ChatRequest(
        session_id="demo-route",
        message="导航到这家机厅",
        intent="navigate",
        shop_id=900001,
        location=ClientLocationContext(lng=121.50, lat=31.22),
    )))

    assert response.route is not None
    assert response.route.provider == "none"
    assert response.map_artifact is not None
    assert response.map_artifact.scene == "agent_route"
    assert "离线路线" in response.reply
    event_names = [event.event for event in container.replay_buffer.list_events("demo-route", None)]
    assert "navigation.route_ready" in event_names
