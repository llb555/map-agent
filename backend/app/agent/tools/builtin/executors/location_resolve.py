"""Executor for the builtin named-place geocoding tool."""

from __future__ import annotations

from app.agent.tools.builtin.provider import BuiltinToolContext


def execute(context: BuiltinToolContext, args: dict[str, object]) -> dict[str, object]:
    tool = context.require("location_resolve_tool")
    query = str(args.get("query") or "").strip()
    province_name = args.get("province_name")
    city_name = args.get("city_name")
    county_name = args.get("county_name")
    locations = tool.resolve(
        query=query,
        province_name=province_name if isinstance(province_name, str) else None,
        city_name=city_name if isinstance(city_name, str) else None,
        county_name=county_name if isinstance(county_name, str) else None,
    )
    return {
        "provider": "amap",
        "query": {
            "query": query,
            "province_name": province_name,
            "city_name": city_name,
            "county_name": county_name,
        },
        "locations": locations,
    }
