"""Executor for the builtin named-place geocoding tool."""

from __future__ import annotations

from typing import Any

from app.agent.tools.builtin.provider import BuiltinToolContext
from app.agent.tools.builtin.query_rewrite import load_or_rewrite


def prepare_arguments(raw_arguments: dict[str, Any], runtime_context: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    args = dict(raw_arguments)
    hydrated: list[str] = []

    query = args.get("query")
    has_query = isinstance(query, str) and query.strip()

    request = runtime_context.get("last_request")
    message = request.get("message") if isinstance(request, dict) else None
    if isinstance(message, str) and message.strip():
        rewritten = load_or_rewrite(runtime_context, fallback_message=message)
        if not has_query:
            resolved_query = rewritten.place_query or rewritten.keyword
            if resolved_query:
                args["query"] = resolved_query
                hydrated.append("query")
        if rewritten.province_name and not args.get("province_name"):
            args["province_name"] = rewritten.province_name
            hydrated.append("province_name")
        if rewritten.city_name and not args.get("city_name"):
            args["city_name"] = rewritten.city_name
            hydrated.append("city_name")
        if rewritten.county_name and not args.get("county_name"):
            args["county_name"] = rewritten.county_name
            hydrated.append("county_name")

    return args, hydrated


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
