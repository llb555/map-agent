"""Generate frontend artifacts from the backend SSE event contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.events.event_types import EVENT_DATA_MODELS, STREAM_EVENT_NAMES, StreamEvent


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "shared" / "schemas" / "chat-stream-event.schema.json"
TS_PATH = REPO_ROOT / "apps" / "web" / "src" / "generated" / "chatStreamContract.ts"

HEADER = """// Generated from backend/app/agent/events/event_types.py.
// Run `backend/.venv/bin/python backend/scripts/generate_stream_contract.py` after editing the backend event models.
// Do not edit by hand.

"""


def _json_type_to_ts(schema: dict[str, Any], *, property_name: str | None = None) -> str:
    if "$ref" in schema:
        ref_name = str(schema["$ref"]).rsplit("/", 1)[-1]
        return ref_name or "Record<string, unknown>"

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        variants = [_json_type_to_ts(item, property_name=property_name) for item in any_of]
        return " | ".join(dict.fromkeys(variants))

    enum = schema.get("enum")
    if isinstance(enum, list):
        return " | ".join(json.dumps(item, ensure_ascii=False) for item in enum)

    const = schema.get("const")
    if const is not None:
        return json.dumps(const, ensure_ascii=False)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(_json_type_to_ts({**schema, "type": item}, property_name=property_name) for item in schema_type)

    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        item_type = _json_type_to_ts(schema.get("items", {}), property_name=property_name)
        return f"Array<{item_type}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return "Record<string, unknown>"
        required = set(schema.get("required", []))
        lines: list[str] = ["{"]
        for key, value in properties.items():
            optional = "" if key in required else "?"
            ts_type = _json_type_to_ts(value, property_name=key)
            lines.append(f"  {key}{optional}: {ts_type};")
        if schema.get("additionalProperties") is not False:
            lines.append("  [key: string]: unknown;")
        lines.append("}")
        return "\n".join(lines)

    if property_name == "data":
        return "Record<string, unknown>"
    return "unknown"


def _schema_to_ts_alias(name: str, schema: dict[str, Any]) -> str:
    return f"export type {name} = {_json_type_to_ts(schema)};\n"


def _schema_definitions(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs")
    if isinstance(defs, dict):
        return defs
    definitions = schema.get("definitions")
    if isinstance(definitions, dict):
        return definitions
    return {}


def build_schema() -> dict[str, Any]:
    """Build a JSON Schema bundle with per-event payload definitions."""
    event_names = list(STREAM_EVENT_NAMES)
    event_data_defs = {
        event_name: model.model_json_schema(mode="validation")
        for event_name, model in EVENT_DATA_MODELS.items()
    }
    nested_defs: dict[str, Any] = {}
    for schema in event_data_defs.values():
        nested_defs.update(_schema_definitions(schema))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://arcadegent.local/schemas/chat-stream-event.schema.json",
        "title": "Arcadegent Chat Stream SSE Event",
        "$defs": {
            "StreamEvent": StreamEvent.model_json_schema(mode="validation"),
            "eventData": event_data_defs,
            **nested_defs,
        },
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "session_id": {"type": "string"},
            "event": {"enum": event_names, "type": "string"},
            "at": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["id", "session_id", "event", "at", "data"],
        "oneOf": [
            {
                "properties": {
                    "event": {"const": event_name},
                    "data": {"$ref": f"#/$defs/eventData/{event_name}"},
                },
            }
            for event_name in event_names
        ],
    }


def build_typescript() -> str:
    """Build TypeScript event names and payload aliases from Pydantic schemas."""
    chunks: list[str] = [HEADER]
    event_names = list(STREAM_EVENT_NAMES)
    chunks.append(f"export const STREAM_EVENT_NAMES = {json.dumps(event_names, indent=2)} as const;\n")
    chunks.append("export type ChatStreamEventName = (typeof STREAM_EVENT_NAMES)[number];\n\n")

    for event_name, model in EVENT_DATA_MODELS.items():
        schema = model.model_json_schema(mode="validation")
        for def_name, def_schema in _schema_definitions(schema).items():
            chunks.append(_schema_to_ts_alias(def_name, def_schema))
            chunks.append("\n")
        alias = "".join(part.capitalize() for part in event_name.replace("_", ".").split("."))
        chunks.append(_schema_to_ts_alias(f"{alias}Data", schema))
        chunks.append("\n")

    data_union = " | ".join(
        "".join(part.capitalize() for part in event_name.replace("_", ".").split(".")) + "Data"
        for event_name in event_names
    )
    chunks.append(f"export type ChatStreamEventData = {data_union};\n\n")
    chunks.append(
        "export type ChatStreamEnvelope = {\n"
        "  id: number;\n"
        "  session_id: string;\n"
        "  event: ChatStreamEventName;\n"
        "  at: string;\n"
        "  data: ChatStreamEventData;\n"
        "};\n\n"
    )
    chunks.append(
        "export function isChatStreamEventName(value: string): value is ChatStreamEventName {\n"
        "  return (STREAM_EVENT_NAMES as readonly string[]).includes(value);\n"
        "}\n"
    )
    return "".join(chunks)


def main() -> None:
    schema = build_schema()
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    TS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    TS_PATH.write_text(build_typescript(), encoding="utf-8")


if __name__ == "__main__":
    main()
