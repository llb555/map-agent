"""HTTP API layer: chat endpoint backed by orchestrator runtime."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from app.agent.runtime.orchestrator import SessionAlreadyRunningError, SessionOwnershipError
from app.agent.runtime.session_state import AgentSessionState, AgentTurn, get_working_memory_artifact
from app.api.deps import get_container
from app.core.container import AppContainer
from app.infra.observability.logger import get_logger
from app.protocol.messages import (
    ChatHistoryTurnDto,
    ChatAttachmentDto,
    ChatRequest,
    ChatResponse,
    ChatSessionDispatchDto,
    ChatSessionDetailDto,
    ChatSessionSummaryDto,
    ClientLocationContext,
    IntentType,
)

router = APIRouter(prefix="/api", tags=["chat"])
logger = get_logger(__name__)


def _normalize_intent(raw: str) -> IntentType:
    if raw == "navigate":
        return "navigate"
    if raw == "search_nearby":
        return "search_nearby"
    return "search"


def _single_line(text: str, *, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(1, limit - 3)].rstrip()}..."


def _build_title(turns: list[AgentTurn]) -> str:
    for turn in turns:
        if turn.role != "user":
            continue
        title = _single_line(turn.content, limit=32)
        if title:
            return title
    return "New chat"


def _build_preview(turns: list[AgentTurn]) -> str | None:
    for turn in reversed(turns):
        if turn.role not in {"assistant", "user"}:
            continue
        preview = _single_line(turn.content, limit=72)
        if preview:
            return preview
    return None


def _to_turn(turn: AgentTurn) -> ChatHistoryTurnDto:
    return ChatHistoryTurnDto(
        role=turn.role,
        content=turn.content,
        name=turn.name,
        call_id=turn.call_id,
        payload=turn.payload or None,
        created_at=turn.created_at,
    )


def _clip_text(value: str, *, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)].rstrip() + "..."


def _extract_text_from_docx_bytes(filename: str, payload: bytes) -> str:
    try:
        with ZipFile(io.BytesIO(payload)) as archive:  # type: ignore[name-defined]
            document = archive.read("word/document.xml")
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"attachment_docx_part_missing:{filename}") from exc
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"attachment_docx_invalid:{filename}") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"attachment_docx_read_failed:{filename}:{exc}") from exc

    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=400, detail=f"attachment_docx_parse_failed:{filename}") from exc
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        runs = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs).strip()


def _extract_text_from_pdf_bytes(filename: str, payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=400, detail="attachment_pdf_unsupported") from exc

    try:
        reader = PdfReader(io.BytesIO(payload))  # type: ignore[name-defined]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"attachment_pdf_read_failed:{filename}") from exc

    parts: list[str] = []
    for page in reader.pages[:8]:
        try:
            text = str(page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_text_from_attachment(filename: str, mime_type: str, payload: bytes) -> str | None:
    suffix = Path(filename).suffix.lower()
    if not payload:
        return None
    if mime_type.startswith("text/") or suffix in {".md", ".txt", ".json", ".jsonl"}:
        return payload.decode("utf-8", errors="ignore").strip() or None
    if suffix == ".docx":
        return _extract_text_from_docx_bytes(filename, payload) or None
    if suffix == ".pdf":
        return _extract_text_from_pdf_bytes(filename, payload) or None
    return None


async def _parse_chat_attachments(files: list[UploadFile]) -> list[ChatAttachmentDto]:
    attachments: list[ChatAttachmentDto] = []
    for item in files:
        filename = Path(item.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="attachment_filename_required")
        payload = await item.read()
        if not payload:
            continue
        if len(payload) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"attachment_too_large:{filename}")
        mime_type = (item.content_type or "application/octet-stream").strip() or "application/octet-stream"
        is_image = mime_type.startswith("image/")
        extracted_text = None if is_image else _extract_text_from_attachment(filename, mime_type, payload)
        image_data_url = None
        preview_text: str | None = None
        if is_image:
            encoded = base64.b64encode(payload).decode("ascii")
            image_data_url = f"data:{mime_type};base64,{encoded}"
            preview_text = f"已附带图片 {filename}"
        elif extracted_text:
            preview_text = _clip_text(extracted_text.replace("\r", "\n"), limit=220)
        else:
            preview_text = f"已附带文件 {filename}"

        attachments.append(
            ChatAttachmentDto(
                name=filename,
                mime_type=mime_type,
                size_bytes=len(payload),
                kind="image" if is_image else "document",
                preview_text=preview_text,
                extracted_text=_clip_text(extracted_text or "", limit=12000) if extracted_text else None,
                image_data_url=image_data_url,
            )
        )
    return attachments


def _request_from_form(
    *,
    session_id: str | None,
    client_id: str | None,
    message: str | None,
    intent: str | None,
    shop_id: str | None,
    location: str | None,
    keyword: str | None,
    province_code: str | None,
    city_code: str | None,
    county_code: str | None,
    page_size: str | None,
    attachments: list[ChatAttachmentDto],
) -> ChatRequest:
    location_payload = None
    if location:
        try:
            decoded = json.loads(location)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="chat_location_invalid_json") from exc
        location_payload = ClientLocationContext.model_validate(decoded)
    return ChatRequest(
        session_id=session_id or None,
        client_id=client_id or None,
        message=(message or "").strip(),
        intent=intent or None,
        shop_id=int(shop_id) if shop_id else None,
        location=location_payload,
        keyword=keyword or None,
        province_code=province_code or None,
        city_code=city_code or None,
        county_code=county_code or None,
        page_size=int(page_size) if page_size else 5,
        attachments=attachments,
    )


def _to_summary(state: AgentSessionState) -> ChatSessionSummaryDto:
    return ChatSessionSummaryDto(
        session_id=state.session_id,
        title=_build_title(state.turns),
        preview=_build_preview(state.turns),
        intent=_normalize_intent(state.intent),
        status=state.status,
        turn_count=len(state.turns),
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _state_shop_rows(state: AgentSessionState) -> list[dict]:
    shops_raw: list[dict] = []
    memory_shops = get_working_memory_artifact(state.working_memory, "shops")
    if isinstance(memory_shops, list):
        shops_raw.extend(item for item in memory_shops if isinstance(item, dict))
    memory_shop = get_working_memory_artifact(state.working_memory, "shop")
    if isinstance(memory_shop, dict):
        source_id = memory_shop.get("source_id")
        exists = any(item.get("source_id") == source_id for item in shops_raw)
        if not exists:
            shops_raw.append(memory_shop)
    return shops_raw[:20]


def _state_client_location(state: AgentSessionState) -> ClientLocationContext | None:
    memory_location = get_working_memory_artifact(state.working_memory, "client_location")
    if not isinstance(memory_location, dict):
        return None
    try:
        return ClientLocationContext.model_validate(memory_location)
    except Exception:
        return None


def _to_detail(state: AgentSessionState, *, container: AppContainer) -> ChatSessionDetailDto:
    raw_shops = _state_shop_rows(state)
    shops = container.arcade_payload_mapper.summaries_from_rows(raw_shops)
    route = container.arcade_payload_mapper.route_from_payload(
        get_working_memory_artifact(state.working_memory, "route")
    )
    destination_raw = get_working_memory_artifact(state.working_memory, "destination")
    if not isinstance(destination_raw, dict) and route is not None:
        destination_raw = raw_shops[0] if raw_shops else None
    destination = (
        container.arcade_payload_mapper.summary_from_row(destination_raw)
        if isinstance(destination_raw, dict)
        else None
    )
    return ChatSessionDetailDto(
        session_id=state.session_id,
        intent=_normalize_intent(state.intent),
        active_subagent=state.active_subagent,
        status=state.status,
        last_error=state.last_error,
        reply=state.working_memory.get("reply") if isinstance(state.working_memory.get("reply"), str) else None,
        shops=shops,
        route=route,
        client_location=_state_client_location(state),
        destination=destination,
        view_payload=get_working_memory_artifact(state.working_memory, "view_payload")
        if isinstance(get_working_memory_artifact(state.working_memory, "view_payload"), dict)
        else None,
        turn_count=len(state.turns),
        created_at=state.created_at,
        updated_at=state.updated_at,
        turns=[_to_turn(turn) for turn in state.turns],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    container: AppContainer = Depends(get_container),
) -> ChatResponse:
    logger.info(
        "api.chat.request session_id=%s intent=%s page_size=%s message=%s",
        request.session_id or "new",
        request.intent or "auto",
        request.page_size,
        " ".join(request.message.split())[:160],
    )
    try:
        response = await container.orchestrator.run_chat(request)
    except SessionAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=404, detail=f"session '{exc.session_id}' not found") from exc
    logger.info(
        "api.chat.response session_id=%s intent=%s shops=%s",
        response.session_id,
        response.intent,
        len(response.shops),
    )
    return response


@router.post("/chat/upload", response_model=ChatResponse)
async def chat_with_upload(
    session_id: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    message: str | None = Form(default=None),
    intent: str | None = Form(default=None),
    shop_id: str | None = Form(default=None),
    location: str | None = Form(default=None),
    keyword: str | None = Form(default=None),
    province_code: str | None = Form(default=None),
    city_code: str | None = Form(default=None),
    county_code: str | None = Form(default=None),
    page_size: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    container: AppContainer = Depends(get_container),
) -> ChatResponse:
    attachments = await _parse_chat_attachments(files)
    request = _request_from_form(
        session_id=session_id,
        client_id=client_id,
        message=message,
        intent=intent,
        shop_id=shop_id,
        location=location,
        keyword=keyword,
        province_code=province_code,
        city_code=city_code,
        county_code=county_code,
        page_size=page_size,
        attachments=attachments,
    )
    return await chat(request=request, container=container)


@router.post(
    "/chat/sessions",
    response_model=ChatSessionDispatchDto,
    status_code=status.HTTP_202_ACCEPTED,
)
async def dispatch_chat_session(
    request: ChatRequest,
    container: AppContainer = Depends(get_container),
) -> ChatSessionDispatchDto:
    logger.info(
        "api.chat.dispatch session_id=%s intent=%s page_size=%s message=%s",
        request.session_id or "new",
        request.intent or "auto",
        request.page_size,
        " ".join(request.message.split())[:160],
    )
    try:
        session_id = await container.orchestrator.dispatch_chat(request)
    except SessionAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SessionOwnershipError as exc:
        raise HTTPException(status_code=404, detail=f"session '{exc.session_id}' not found") from exc
    return ChatSessionDispatchDto(session_id=session_id, status="running")


@router.post(
    "/chat/sessions/upload",
    response_model=ChatSessionDispatchDto,
    status_code=status.HTTP_202_ACCEPTED,
)
async def dispatch_chat_session_with_upload(
    session_id: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    message: str | None = Form(default=None),
    intent: str | None = Form(default=None),
    shop_id: str | None = Form(default=None),
    location: str | None = Form(default=None),
    keyword: str | None = Form(default=None),
    province_code: str | None = Form(default=None),
    city_code: str | None = Form(default=None),
    county_code: str | None = Form(default=None),
    page_size: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    container: AppContainer = Depends(get_container),
) -> ChatSessionDispatchDto:
    attachments = await _parse_chat_attachments(files)
    request = _request_from_form(
        session_id=session_id,
        client_id=client_id,
        message=message,
        intent=intent,
        shop_id=shop_id,
        location=location,
        keyword=keyword,
        province_code=province_code,
        city_code=city_code,
        county_code=county_code,
        page_size=page_size,
        attachments=attachments,
    )
    return await dispatch_chat_session(request=request, container=container)


@router.get("/chat/sessions", response_model=list[ChatSessionSummaryDto])
def list_chat_sessions(
    limit: int = Query(default=40, ge=1, le=200),
    client_id: str | None = Query(default=None, min_length=1, max_length=128),
    container: AppContainer = Depends(get_container),
) -> list[ChatSessionSummaryDto]:
    sessions = container.session_store.list_snapshots(limit=limit, client_id=client_id)
    return [_to_summary(state) for state in sessions if state.turns or state.status == "running"]


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetailDto)
def get_chat_session(
    session_id: str,
    client_id: str | None = Query(default=None, min_length=1, max_length=128),
    container: AppContainer = Depends(get_container),
) -> ChatSessionDetailDto:
    session = container.session_store.snapshot(session_id, client_id=client_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    return _to_detail(session, container=container)


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(
    session_id: str,
    client_id: str | None = Query(default=None, min_length=1, max_length=128),
    container: AppContainer = Depends(get_container),
) -> Response:
    session = container.session_store.snapshot(session_id, client_id=client_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    if container.orchestrator.is_session_running(session_id):
        raise HTTPException(status_code=409, detail=f"session '{session_id}' is currently running")
    deleted = container.session_store.delete(session_id, client_id=client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
