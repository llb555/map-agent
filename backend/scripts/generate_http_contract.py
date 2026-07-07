"""Generate frontend TypeScript DTOs from FastAPI OpenAPI components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api.http.arcades import router as arcades_router
from app.api.http.chat import router as chat_router
from app.api.http.health import router as health_router
from app.api.http.knowledge import router as knowledge_router
from app.api.http.location import router as location_router
from app.api.http.regions import router as regions_router
from app.api.stream.sse import router as sse_router


REPO_ROOT = Path(__file__).resolve().parents[2]
TS_PATH = REPO_ROOT / "apps" / "web" / "src" / "generated" / "httpContract.ts"

HEADER = """// Generated from FastAPI OpenAPI components.
// Run `backend/.venv/bin/python backend/scripts/generate_http_contract.py` after editing backend DTOs.
// Do not edit by hand.

"""

ALIASES = {
    "ArcadeShopSummaryDto": "ArcadeSummaryDto",
    "ArcadeShopDetailDto": "ArcadeDetailDto",
    "PagedArcadeResponse": "PagedArcadesDto",
    "ChatSessionStatusType": "ChatSessionStatusDto",
}


def _type_name(name: str) -> str:
    return ALIASES.get(name, name)


def _prop_name(name: str) -> str:
    return name if name.replace("_", "").isalnum() else json.dumps(name)


def _schema_to_ts(schema: dict[str, Any], components: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _type_name(str(schema["$ref"]).rsplit("/", 1)[-1])
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    enum = schema.get("enum")
    if isinstance(enum, list):
        return " | ".join(json.dumps(item, ensure_ascii=False) for item in enum)
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        return " | ".join(dict.fromkeys(_schema_to_ts(item, components) for item in any_of))
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        return " & ".join(dict.fromkeys(_schema_to_ts(item, components) for item in all_of))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(_schema_to_ts({**schema, "type": item}, components) for item in schema_type)
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        return f"Array<{_schema_to_ts(schema.get('items', {}), components)}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties")
        additional = schema.get("additionalProperties")
        if not isinstance(properties, dict):
            if isinstance(additional, dict):
                return f"Record<string, {_schema_to_ts(additional, components)}>"
            return "Record<string, unknown>"
        required = set(schema.get("required", []))
        lines = ["{"]
        for key, prop_schema in properties.items():
            optional = "" if key in required else "?"
            lines.append(f"  {_prop_name(key)}{optional}: {_schema_to_ts(prop_schema, components)};")
        if additional is not False:
            lines.append("  [key: string]: unknown;")
        lines.append("}")
        return "\n".join(lines)
    return "unknown"


def build_typescript() -> str:
    app = FastAPI(title="Arcadegent Contract Generator")
    app.include_router(health_router)
    app.include_router(knowledge_router)
    app.include_router(arcades_router)
    app.include_router(location_router)
    app.include_router(regions_router)
    app.include_router(chat_router)
    app.include_router(sse_router)
    openapi = app.openapi()
    components = openapi.get("components", {}).get("schemas", {})
    if not isinstance(components, dict):
        components = {}

    chunks = [HEADER]
    for name in sorted(components):
        schema = components[name]
        if not isinstance(schema, dict):
            continue
        chunks.append(f"export type {_type_name(name)} = {_schema_to_ts(schema, components)};\n\n")
    return "".join(chunks)


def main() -> None:
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TS_PATH.write_text(build_typescript(), encoding="utf-8")


if __name__ == "__main__":
    main()
