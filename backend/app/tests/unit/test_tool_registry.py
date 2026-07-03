"""Unit tests for tool registry validation and dispatch behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import FastMCP

from app.agent.tools.builtin import BuiltinToolProvider
from app.agent.tools.mcp_gateway import MCPServerConfig, MCPToolGateway
from app.agent.tools.permission import ToolPermissionChecker
from app.agent.tools.registry import ToolRegistry
from app.core.config import Settings
from app.infra.db.local_store import LocalArcadeStore


def _run(awaitable):
    return asyncio.run(awaitable)


def _write_rows(path: Path) -> None:
    rows = [
        {
            "source": "bemanicn",
            "source_id": 1,
            "source_url": "https://map.bemanicn.com/s/1",
            "name": "Alpha Arcade",
            "province_code": "110000000000",
            "province_name": "Beijing",
            "city_code": "110100000000",
            "city_name": "Beijing",
            "county_code": "110101000000",
            "county_name": "Dongcheng",
            "arcades": [{"title_name": "maimai", "quantity": 2}],
        }
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _build_registry(
    tmp_path: Path,
    *,
    mcp_tool_gateway: MCPToolGateway | None = None,
    extra_runtime_services: dict[str, object] | None = None,
) -> ToolRegistry:
    data_path = tmp_path / "shops.jsonl"
    _write_rows(data_path)
    store = LocalArcadeStore.from_jsonl(data_path)
    gateway = mcp_tool_gateway or MCPToolGateway()
    return ToolRegistry(
        providers=[
            BuiltinToolProvider(
                runtime_services={
                    "store": store,
                    "mcp_tool_gateway": gateway,
                    "settings": Settings(),
                    **(extra_runtime_services or {}),
                }
            ),
            gateway,
        ],
        permission_checker=ToolPermissionChecker(policy_file=tmp_path / "missing.yaml"),
        strict_schema=True,
    )


def _build_mcp_gateway() -> MCPToolGateway:
    mcp = FastMCP("Test AMap MCP")

    @mcp.tool(name="maps_direction_walking", description="步行路径规划，输入 origin 和 destination，输出 paths。")
    def maps_direction_walking(origin: str, destination: str) -> dict[str, object]:
        return {
            "origin": origin,
            "destination": destination,
            "paths": [
                {
                    "distance": 1234,
                    "duration": 678,
                    "steps": [
                        {
                            "instruction": "walk forward",
                            "polyline": "116.3,39.9;116.4,39.91",
                        }
                    ],
                }
            ],
        }

    gateway = MCPToolGateway(
        servers=[
            MCPServerConfig(
                name="amap",
                enabled=True,
                source=mcp,
                url="memory://amap",
                timeout_seconds=3,
                route_tool_name="maps_direction_walking",
            )
        ]
    )
    _run(gateway.refresh())
    return gateway


def test_tool_registry_returns_validation_error_for_bad_args(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path)
    result = _run(registry.execute(
        call_id="c1",
        tool_name="route_plan_tool",
        raw_arguments={
            "provider": "amap",
            "mode": "walking",
            "origin": {"lng": 116.3, "lat": 39.9},
            "destination": {"lng": 116.4},
        },
        allowed_tools=["route_plan_tool"],
    ))
    assert result.status == "failed"
    assert result.output["error"]["type"] == "validation_error"


def test_tool_registry_can_lookup_one_shop(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path)
    result = _run(registry.execute(
        call_id="c2",
        tool_name="db_query_tool",
        raw_arguments={
            "keyword": None,
            "province_code": None,
            "city_code": None,
            "county_code": None,
            "has_arcades": None,
            "page": 1,
            "page_size": 1,
            "shop_id": 1,
        },
        allowed_tools=["db_query_tool"],
    ))
    assert result.status == "completed"
    assert result.output["shop"]["source_id"] == 1


def test_tool_registry_can_resolve_named_place_without_mcp_geocode(tmp_path: Path) -> None:
    class _StubResolver:
        def geocode_one(self, raw: dict[str, object]):
            from app.protocol.messages import ArcadeGeoDto, GeoPoint

            assert raw["name"] == "大雁塔"
            return ArcadeGeoDto(
                gcj02=GeoPoint(
                    lng=108.960987,
                    lat=34.219447,
                    coord_system="gcj02",
                    source="geocode",
                    precision="approx",
                ),
                wgs84=None,
                source="geocode",
                precision="approx",
            )

    registry = _build_registry(
        tmp_path,
        extra_runtime_services={"arcade_geo_resolver": _StubResolver()},
    )
    result = _run(registry.execute(
        call_id="c2b",
        tool_name="location_resolve_tool",
        raw_arguments={
            "query": "大雁塔",
            "city_name": "西安",
            "county_name": "雁塔区",
        },
        allowed_tools=["location_resolve_tool"],
    ))
    assert result.status == "completed"
    assert result.output["provider"] == "amap"
    assert result.output["locations"][0]["name"] == "大雁塔"
    assert result.output["locations"][0]["lng"] == 108.960987


def test_tool_registry_prepares_location_resolve_args_from_query_rewrite(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path)

    args, hydrated = registry._providers[0].prepare_arguments(
        tool_name="location_resolve_tool",
        raw_arguments={},
        runtime_context={
            "last_request": {
                "message": "魔都浦东人广附近有舞萌吗",
            }
        },
    )

    assert args["query"] == "人民广场"
    assert args["province_name"] == "上海"
    assert args["city_name"] == "上海"
    assert args["county_name"] == "浦东新区"
    assert "query" in hydrated


def test_tool_registry_normalizes_city_name_in_city_code_field(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path)
    result = _run(registry.execute(
        call_id="c3",
        tool_name="db_query_tool",
        raw_arguments={
            "keyword": "maimai",
            "province_code": None,
            "city_code": "Beijing",
            "county_code": None,
            "province_name": None,
            "city_name": None,
            "county_name": None,
            "has_arcades": True,
            "page": 1,
            "page_size": 10,
            "shop_id": None,
        },
        allowed_tools=["db_query_tool"],
    ))
    assert result.status == "completed"
    assert result.output["total"] == 1
    assert result.output["shops"][0]["source_id"] == 1


def test_tool_registry_supports_title_quantity_sorting(tmp_path: Path) -> None:
    data_path = tmp_path / "shops_sort.jsonl"
    rows = [
        {
            "source": "bemanicn",
            "source_id": 1,
            "source_url": "https://map.bemanicn.com/s/1",
            "name": "Alpha Arcade",
            "arcades": [{"title_name": "maimai", "quantity": 1}],
        },
        {
            "source": "bemanicn",
            "source_id": 2,
            "source_url": "https://map.bemanicn.com/s/2",
            "name": "Beta Arcade",
            "arcades": [{"title_name": "maimai", "quantity": 3}],
        },
        {
            "source": "bemanicn",
            "source_id": 3,
            "source_url": "https://map.bemanicn.com/s/3",
            "name": "Gamma Arcade",
            "arcades": [{"title_name": "sdvx", "quantity": 5}],
        },
    ]
    with data_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")

    store = LocalArcadeStore.from_jsonl(data_path)
    gateway = MCPToolGateway()
    registry = ToolRegistry(
        providers=[
            BuiltinToolProvider(
                runtime_services={
                    "store": store,
                    "mcp_tool_gateway": gateway,
                }
            ),
            gateway,
        ],
        permission_checker=ToolPermissionChecker(policy_file=tmp_path / "missing.yaml"),
        strict_schema=True,
    )
    result = _run(registry.execute(
        call_id="c4",
        tool_name="db_query_tool",
        raw_arguments={
            "keyword": None,
            "has_arcades": True,
            "sort_by": "title_quantity",
            "sort_order": "desc",
            "sort_title_name": "maimai",
            "page": 1,
            "page_size": 10,
        },
        allowed_tools=["db_query_tool"],
    ))
    assert result.status == "completed"
    assert result.output["total"] == 3
    assert [row["source_id"] for row in result.output["shops"]] == [2, 1, 3]
    assert result.output["query"]["sort_by"] == "title_quantity"
    assert result.output["query"]["sort_order"] == "desc"
    assert result.output["query"]["sort_title_name"] == "maimai"


def test_tool_registry_backfills_sort_title_name_from_keyword(tmp_path: Path) -> None:
    data_path = tmp_path / "shops_sort_keyword.jsonl"
    rows = [
        {
            "source": "bemanicn",
            "source_id": 1,
            "source_url": "https://map.bemanicn.com/s/1",
            "name": "Alpha Arcade",
            "arcades": [{"title_name": "maimai DX", "quantity": 2}],
        },
        {
            "source": "bemanicn",
            "source_id": 2,
            "source_url": "https://map.bemanicn.com/s/2",
            "name": "Beta Arcade",
            "arcades": [{"title_name": "maimai DX", "quantity": 5}],
        },
    ]
    with data_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")

    store = LocalArcadeStore.from_jsonl(data_path)
    gateway = MCPToolGateway()
    registry = ToolRegistry(
        providers=[
            BuiltinToolProvider(
                runtime_services={
                    "store": store,
                    "mcp_tool_gateway": gateway,
                }
            ),
            gateway,
        ],
        permission_checker=ToolPermissionChecker(policy_file=tmp_path / "missing.yaml"),
        strict_schema=True,
    )
    result = _run(registry.execute(
        call_id="c5",
        tool_name="db_query_tool",
        raw_arguments={
            "keyword": "maimai",
            "has_arcades": True,
            "sort_by": "title_quantity",
            "sort_order": "desc",
            "sort_title_name": None,
            "page": 1,
            "page_size": 10,
        },
        allowed_tools=["db_query_tool"],
    ))
    assert result.status == "completed"
    assert [row["source_id"] for row in result.output["shops"]] == [2, 1]
    assert result.output["query"]["sort_title_name"] == "maimai"


def test_tool_registry_supports_distance_sorting(tmp_path: Path) -> None:
    data_path = tmp_path / "shops_distance.jsonl"
    rows = [
        {
            "source": "bemanicn",
            "source_id": 1,
            "source_url": "https://map.bemanicn.com/s/1",
            "name": "Near Arcade",
            "longitude_wgs84": 116.397428,
            "latitude_wgs84": 39.90923,
            "arcades": [{"title_name": "maimai", "quantity": 1}],
        },
        {
            "source": "bemanicn",
            "source_id": 2,
            "source_url": "https://map.bemanicn.com/s/2",
            "name": "Far Arcade",
            "longitude_wgs84": 116.407428,
            "latitude_wgs84": 39.91923,
            "arcades": [{"title_name": "maimai", "quantity": 1}],
        },
    ]
    with data_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")

    store = LocalArcadeStore.from_jsonl(data_path)
    gateway = MCPToolGateway()
    registry = ToolRegistry(
        providers=[
            BuiltinToolProvider(
                runtime_services={
                    "store": store,
                    "mcp_tool_gateway": gateway,
                }
            ),
            gateway,
        ],
        permission_checker=ToolPermissionChecker(policy_file=tmp_path / "missing.yaml"),
        strict_schema=True,
    )
    result = _run(registry.execute(
        call_id="c_distance",
        tool_name="db_query_tool",
        raw_arguments={
            "has_arcades": True,
            "sort_by": "distance",
            "sort_order": "asc",
            "origin_lng": 116.397428,
            "origin_lat": 39.90923,
            "origin_coord_system": "wgs84",
            "page": 1,
            "page_size": 10,
        },
        allowed_tools=["db_query_tool"],
    ))
    assert result.status == "completed"
    assert [row["source_id"] for row in result.output["shops"]] == [1, 2]
    assert result.output["shops"][0]["distance_m"] == 0
    assert result.output["query"]["sort_by"] == "distance"
    assert result.output["query"]["origin_coord_system"] == "wgs84"


def test_tool_registry_includes_discovered_mcp_tools_when_allowed(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path, mcp_tool_gateway=_build_mcp_gateway())

    definitions = _run(registry.tool_definitions(allowed_tools=["route_plan_tool", "mcp__*"]))
    names = [
        item["function"]["name"]
        for item in definitions
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]

    assert "route_plan_tool" in names
    assert "mcp__amap__maps_direction_walking" in names


def test_tool_registry_gettools_aggregates_builtin_and_mcp_tools(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path, mcp_tool_gateway=_build_mcp_gateway())

    tools = _run(registry.gettools())

    assert "db_query_tool" in tools
    assert "knowledge_search_tool" in tools
    assert tools["db_query_tool"].provider == "builtin"
    assert "mcp__amap__maps_direction_walking" in tools
    assert tools["mcp__amap__maps_direction_walking"].provider == "mcp"
    assert tools["summary_tool"].metadata["prompt"].endswith("response_composition.md")


def test_tool_registry_can_execute_knowledge_search_tool(tmp_path: Path) -> None:
    class _FakeRAGService:
        def search(self, *, query: str, top_k: int) -> dict[str, object]:
            return {
                "status": "completed",
                "backend": "langchain_memory",
                "query": {"text": query, "top_k": top_k},
                "hits": [
                    {
                        "title": "Gamma 评论",
                        "source_uri": "knowledge://gamma",
                        "source_type": "jsonl",
                        "score": 0.92,
                        "snippet": "机器维护不错。",
                        "metadata": {},
                    }
                ],
            }

    registry = _build_registry(
        tmp_path,
        extra_runtime_services={"knowledge_rag_service": _FakeRAGService()},
    )

    result = _run(registry.execute(
        call_id="c_knowledge",
        tool_name="knowledge_search_tool",
        raw_arguments={"query": "Gamma 评论怎么样", "top_k": 3},
        allowed_tools=["knowledge_search_tool"],
    ))

    assert result.status == "completed"
    assert result.output["hits"][0]["title"] == "Gamma 评论"


def test_tool_registry_can_execute_discovered_mcp_tool(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path, mcp_tool_gateway=_build_mcp_gateway())

    result = _run(registry.execute(
        call_id="c6",
        tool_name="mcp__amap__maps_direction_walking",
        raw_arguments={
            "origin": "116.3,39.9",
            "destination": "116.4,39.91",
        },
        allowed_tools=["mcp__*"],
    ))

    assert result.status == "completed"
    assert result.output["server"] == "amap"
    assert result.output["tool"] == "maps_direction_walking"
    assert result.output["route"]["distance_m"] == 1234
    assert result.output["route"]["duration_s"] == 678


def test_route_plan_tool_prefers_amap_mcp_when_available(tmp_path: Path) -> None:
    registry = _build_registry(tmp_path, mcp_tool_gateway=_build_mcp_gateway())

    result = _run(registry.execute(
        call_id="c7",
        tool_name="route_plan_tool",
        raw_arguments={
            "provider": "amap",
            "mode": "walking",
            "origin": {"lng": 116.3, "lat": 39.9},
            "destination": {"lng": 116.4, "lat": 39.91},
        },
        allowed_tools=["route_plan_tool", "mcp__*"],
    ))

    assert result.status == "completed"
    assert result.output["route"]["provider"] == "amap"
    assert result.output["route"]["distance_m"] == 1234
    assert result.output["route"]["duration_s"] == 678
