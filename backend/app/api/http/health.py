"""HTTP API layer: health and readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.core.container import AppContainer

router = APIRouter(tags=["health"])


@router.get("/health")
def health(container: AppContainer = Depends(get_container)) -> dict:
    return {
        "status": "ok",
        "store": container.store.health(),
        "rag": container.rag_service.health(),
        "env": container.settings.env,
        "demo_mode": container.settings.demo_mode,
        "llm_configured": bool(container.settings.llm_api_key),
        "degradation": "deterministic_local_runtime" if container.settings.demo_mode else None,
        "tool_providers": container.tool_registry.provider_health(),
        "mcp": container.tool_registry.mcp_health(),
    }
