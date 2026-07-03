"""Executor for the builtin LangChain-backed knowledge retrieval tool."""

from __future__ import annotations

from typing import Any

from app.agent.tools.builtin.provider import BuiltinToolContext
from app.agent.tools.builtin.query_rewrite import load_or_rewrite


def prepare_arguments(raw_arguments: dict[str, Any], runtime_context: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    args = dict(raw_arguments)
    hydrated: list[str] = []
    query = args.get("query")
    if isinstance(query, str) and query.strip():
        return args, hydrated

    request = runtime_context.get("last_request")
    if isinstance(request, dict):
        message = request.get("message")
        if isinstance(message, str) and message.strip():
            rewritten = load_or_rewrite(runtime_context, fallback_message=message)
            args["query"] = rewritten.knowledge_query or message.strip()
            hydrated.append("query")
            return args, hydrated

    keyword = runtime_context.get("keyword")
    if isinstance(keyword, str) and keyword.strip():
        args["query"] = keyword.strip()
        hydrated.append("query")
    return args, hydrated


def execute(context: BuiltinToolContext, args: dict[str, Any]) -> dict[str, Any]:
    service = context.require("knowledge_rag_service")
    query = str(args.get("query") or "").strip()
    top_k = int(args.get("top_k") or 4)
    return service.search(query=query, top_k=top_k)
