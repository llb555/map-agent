"""HTTP API layer: knowledge base upload and reindex management."""

from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_container, require_admin, require_authenticated_user
from app.auth.models import CurrentUser
from app.core.container import AppContainer
from app.protocol.messages import (
    ArcadeGeoDto,
    GeoPoint,
    KnowledgeArcadeCandidateDto,
    KnowledgeFileItemDto,
    KnowledgeLookupHitDto,
    KnowledgeLookupResponseDto,
    KnowledgeStatusDto,
    KnowledgeUploadResponseDto,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeBatchDeleteRequest(BaseModel):
    relative_paths: list[str] = Field(default_factory=list)


class KnowledgeRetryRequest(BaseModel):
    relative_path: str = Field(..., min_length=1)


class KnowledgeArcadePromotionRequest(BaseModel):
    candidate: KnowledgeArcadeCandidateDto


class KnowledgeArcadePromotionResponse(BaseModel):
    status: Literal["created"]
    source_id: int
    name: str


class KnowledgeSubmissionDto(BaseModel):
    id: str
    owner_user_id: str
    owner_email: str | None
    original_filename: str
    suffix: str
    size_bytes: int
    sha256: str
    title: str | None
    description: str | None
    status: Literal["pending", "approved", "rejected", "withdrawn"]
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: str | None
    published_relative_path: str | None
    created_at: str
    updated_at: str


class KnowledgeSubmissionReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)


def _submission_dto(item: object) -> KnowledgeSubmissionDto:
    return KnowledgeSubmissionDto.model_validate(item, from_attributes=True)


def _build_knowledge_status(container: AppContainer) -> KnowledgeStatusDto:
    rag_health = container.rag_service.health()
    files = [
        KnowledgeFileItemDto(**item)
        for item in container.rag_service.list_source_files()
    ]
    return KnowledgeStatusDto(
        directory=str(container.rag_service.knowledge_directory()),
        enabled=bool(rag_health.get("enabled")),
        source_exists=bool(rag_health.get("source_exists")),
        source_is_dir=bool(rag_health.get("source_is_dir")),
        supported_suffixes=list(rag_health.get("supported_suffixes") or []),
        semantic_chunking_enabled=bool(rag_health.get("semantic_chunking_enabled")),
        reranker_enabled=bool(rag_health.get("reranker_enabled")),
        hybrid_search_enabled=bool(rag_health.get("hybrid_search_enabled")),
        index_ready=bool(rag_health.get("index_ready")),
        chunk_count=int(rag_health.get("chunk_count") or 0),
        pending_count=int(rag_health.get("pending_count") or 0),
        indexing_count=int(rag_health.get("indexing_count") or 0),
        ready_count=int(rag_health.get("ready_count") or 0),
        failed_count=int(rag_health.get("failed_count") or 0),
        job_count=int(rag_health.get("job_count") or 0),
        active_job_id=str(rag_health.get("active_job_id")) if rag_health.get("active_job_id") is not None else None,
        load_error=str(rag_health.get("load_error")) if rag_health.get("load_error") is not None else None,
        files=files,
    )


def _require_knowledge_directory(container: AppContainer) -> Path:
    target_dir = container.rag_service.knowledge_directory()
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="knowledge_directory_unavailable")
    return target_dir


def _resolve_knowledge_relative_path(relative_path: str, *, target_dir: Path) -> Path:
    normalized = Path(relative_path.strip())
    if not normalized.as_posix() or normalized.is_absolute() or ".." in normalized.parts:
        raise HTTPException(status_code=400, detail="knowledge_relative_path_invalid")

    target_path = (target_dir / normalized).resolve()
    try:
        target_path.relative_to(target_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="knowledge_relative_path_outside_root") from exc
    return target_path


def _pick_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _pick_optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_knowledge_arcade_candidate(hit: dict[str, Any]) -> KnowledgeArcadeCandidateDto | None:
    metadata = hit.get("metadata")
    if not isinstance(metadata, dict):
        return None

    name = _pick_optional_str(metadata.get("shop_name")) or _pick_optional_str(metadata.get("name"))
    address = _pick_optional_str(metadata.get("address"))
    city_name = _pick_optional_str(metadata.get("city_name")) or _pick_optional_str(metadata.get("city"))
    province_name = _pick_optional_str(metadata.get("province_name")) or _pick_optional_str(metadata.get("province"))
    county_name = (
        _pick_optional_str(metadata.get("county_name"))
        or _pick_optional_str(metadata.get("district"))
        or _pick_optional_str(metadata.get("district_name"))
    )
    transport = _pick_optional_str(metadata.get("transport"))

    if not name or not (address or city_name or province_name or county_name):
        return None

    lng_gcj = _pick_optional_float(metadata.get("longitude_gcj02")) or _pick_optional_float(metadata.get("lng_gcj02"))
    lat_gcj = _pick_optional_float(metadata.get("latitude_gcj02")) or _pick_optional_float(metadata.get("lat_gcj02"))
    lng_wgs = _pick_optional_float(metadata.get("longitude_wgs84")) or _pick_optional_float(metadata.get("lng_wgs84"))
    lat_wgs = _pick_optional_float(metadata.get("latitude_wgs84")) or _pick_optional_float(metadata.get("lat_wgs84"))

    gcj_point = (
        GeoPoint(
            lng=lng_gcj,
            lat=lat_gcj,
            coord_system="gcj02",
            source="catalog",
            precision="exact",
        )
        if lng_gcj is not None and lat_gcj is not None
        else None
    )
    wgs_point = (
        GeoPoint(
            lng=lng_wgs,
            lat=lat_wgs,
            coord_system="wgs84",
            source="catalog",
            precision="exact",
        )
        if lng_wgs is not None and lat_wgs is not None
        else None
    )
    geo = ArcadeGeoDto(gcj02=gcj_point, wgs84=wgs_point, source="catalog", precision="exact") if (gcj_point or wgs_point) else None

    region_text = " / ".join(part for part in [province_name, city_name, county_name] if part)
    source_uri = _pick_optional_str(hit.get("source_uri"))
    source_type = _pick_optional_str(hit.get("source_type"))
    fingerprint = hashlib.sha1(
        "|".join(
            [
                name,
                address or "",
                city_name or "",
                county_name or "",
                source_uri or "",
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]

    return KnowledgeArcadeCandidateDto(
        id=f"knowledge-{fingerprint}",
        name=name,
        address=address,
        region_text=region_text or None,
        province_name=province_name,
        city_name=city_name,
        county_name=county_name,
        transport=transport,
        source_uri=source_uri,
        source_type=source_type,
        score=float(hit["score"]) if hit.get("score") is not None else None,
        geo=geo,
    )


def _enrich_knowledge_arcade_candidate(
    candidate: KnowledgeArcadeCandidateDto,
    *,
    container: AppContainer,
) -> KnowledgeArcadeCandidateDto:
    if candidate.geo is not None:
        return candidate

    raw = {
        "source_id": -1,
        "name": candidate.name,
        "address": candidate.address,
        "city_name": candidate.city_name,
        "updated_at": candidate.source_uri or candidate.id,
    }
    geo = container.arcade_geo_resolver.geocode_one(raw)
    if geo is None:
        return candidate
    return candidate.model_copy(update={"geo": geo})


@router.get("/status", response_model=KnowledgeStatusDto)
def knowledge_status(container: AppContainer = Depends(get_container)) -> KnowledgeStatusDto:
    return _build_knowledge_status(container)


@router.get("/lookup", response_model=KnowledgeLookupResponseDto)
def lookup_knowledge(
    q: str,
    top_k: int = 3,
    container: AppContainer = Depends(get_container),
) -> KnowledgeLookupResponseDto:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="knowledge_query_required")
    result = container.rag_service.search(query=query, top_k=max(1, min(top_k, 5)))
    hits = [
        KnowledgeLookupHitDto(
            title=item.get("title"),
            source_uri=item.get("source_uri"),
            source_type=item.get("source_type"),
            score=float(item["score"]) if item.get("score") is not None else None,
            snippet=item.get("snippet"),
        )
        for item in (result.get("hits") or [])
        if isinstance(item, dict)
    ]
    candidates: list[KnowledgeArcadeCandidateDto] = []
    seen_candidate_ids: set[str] = set()
    for item in (result.get("hits") or []):
        if not isinstance(item, dict):
            continue
        candidate = _build_knowledge_arcade_candidate(item)
        if candidate is None:
            continue
        candidate = _enrich_knowledge_arcade_candidate(candidate, container=container)
        if candidate.id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(candidate.id)
        candidates.append(candidate)
    return KnowledgeLookupResponseDto(
        query=query,
        status=str(result.get("status") or "unknown"),
        total_hits=int(result.get("total_hits") or len(hits)),
        hits=hits,
        arcade_candidates=candidates,
    )


@router.post("/arcade-candidates/promote", response_model=KnowledgeArcadePromotionResponse, status_code=201)
def promote_knowledge_arcade_candidate(
    payload: KnowledgeArcadePromotionRequest,
    container: AppContainer = Depends(get_container),
    _: CurrentUser = Depends(require_admin),
) -> KnowledgeArcadePromotionResponse:
    candidate = payload.candidate
    gcj = candidate.geo.gcj02 if candidate.geo is not None else None
    wgs = candidate.geo.wgs84 if candidate.geo is not None else None
    proposed = {
        "name": candidate.name.strip(),
        "address": candidate.address,
        "transport": candidate.transport,
        "province_name": candidate.province_name,
        "city_name": candidate.city_name,
        "county_name": candidate.county_name,
        "longitude_gcj02": gcj.lng if gcj is not None else None,
        "latitude_gcj02": gcj.lat if gcj is not None else None,
        "longitude_wgs84": wgs.lng if wgs is not None else None,
        "latitude_wgs84": wgs.lat if wgs is not None else None,
        "source_url": candidate.source_uri or candidate.id,
        "comment": f"由知识库候选审核入库；来源：{candidate.source_uri or candidate.id}",
        "arcades": [],
    }
    if not proposed["name"] or not (proposed["address"] or proposed["city_name"] or proposed["province_name"]):
        raise HTTPException(status_code=400, detail="knowledge_arcade_candidate_incomplete")
    duplicate = container.store.find_duplicate_shop(proposed)
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"knowledge_arcade_candidate_duplicate:{duplicate.get('source_id')}",
        )
    try:
        created = container.store.add_knowledge_shop(proposed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return KnowledgeArcadePromotionResponse(
        status="created",
        source_id=int(created["source_id"]),
        name=str(created["name"]),
    )


@router.get("/submissions", response_model=list[KnowledgeSubmissionDto])
def list_knowledge_submissions(
    container: AppContainer = Depends(get_container),
    user: CurrentUser = Depends(require_authenticated_user),
) -> list[KnowledgeSubmissionDto]:
    owner_scope = None if user.is_admin else user.id
    return [_submission_dto(item) for item in container.knowledge_submission_store.list(owner_user_id=owner_scope)]


@router.post("/submissions", response_model=KnowledgeSubmissionDto, status_code=201)
async def create_knowledge_submission(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=200),
    description: str | None = Form(default=None, max_length=2000),
    container: AppContainer = Depends(get_container),
    user: CurrentUser = Depends(require_authenticated_user),
) -> KnowledgeSubmissionDto:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="knowledge_filename_required")
    suffix = Path(filename).suffix.lower()
    if suffix not in set(container.rag_service.supported_suffixes()):
        raise HTTPException(status_code=400, detail=f"knowledge_suffix_not_supported:{suffix or 'none'}")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="knowledge_submission_empty")
    if len(payload) > container.settings.knowledge_submission_max_bytes:
        raise HTTPException(status_code=413, detail="knowledge_submission_too_large")
    normalized_title = (title or "").strip() or None
    normalized_description = (description or "").strip() or None
    screening = container.knowledge_submission_filter.screen(
        filename=filename,
        payload=payload,
        title=normalized_title,
        description=normalized_description,
    )
    try:
        item = container.knowledge_submission_store.create(
            owner_user_id=user.id,
            owner_email=user.email,
            filename=filename,
            payload=payload,
            title=normalized_title,
            description=normalized_description,
            automated_rejection_note=None if screening.accepted else screening.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _submission_dto(item)


@router.delete("/submissions/{submission_id}", status_code=204, response_class=Response)
def withdraw_knowledge_submission(
    submission_id: str,
    container: AppContainer = Depends(get_container),
    user: CurrentUser = Depends(require_authenticated_user),
) -> Response:
    try:
        item = container.knowledge_submission_store.withdraw(submission_id, owner_user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge_submission_not_found")
    return Response(status_code=204)


@router.post("/submissions/{submission_id}/review", response_model=KnowledgeSubmissionDto)
def review_knowledge_submission(
    submission_id: str,
    payload: KnowledgeSubmissionReviewRequest,
    container: AppContainer = Depends(get_container),
    user: CurrentUser | None = Depends(require_admin),
) -> KnowledgeSubmissionDto:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    try:
        item = container.knowledge_submission_store.review(
            submission_id,
            reviewer_id=user.id,
            decision=payload.decision,
            note=(payload.note or "").strip() or None,
            published_directory=container.rag_service.knowledge_directory(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge_submission_not_found")
    if payload.decision == "approved" and item.published_relative_path:
        container.rag_service.enqueue_reindex(
            relative_paths=[item.published_relative_path],
            kind="submission_approved",
        )
    return _submission_dto(item)


@router.post("/reindex", response_model=KnowledgeStatusDto)
def reindex_knowledge(
    container: AppContainer = Depends(get_container),
    _: CurrentUser | None = Depends(require_admin),
) -> KnowledgeStatusDto:
    try:
        container.rag_service.enqueue_reindex(kind="full_reindex")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc
    return _build_knowledge_status(container)


@router.post("/files/retry", response_model=KnowledgeStatusDto)
def retry_knowledge_file(
    payload: KnowledgeRetryRequest,
    container: AppContainer = Depends(get_container),
    _: CurrentUser | None = Depends(require_admin),
) -> KnowledgeStatusDto:
    try:
        container.rag_service.retry_failed_file(payload.relative_path.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc
    return _build_knowledge_status(container)


@router.post("/upload", response_model=KnowledgeUploadResponseDto)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
    _: CurrentUser | None = Depends(require_admin),
) -> KnowledgeUploadResponseDto:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="knowledge_filename_required")

    suffix = Path(filename).suffix.lower()
    supported = set(container.rag_service.supported_suffixes())
    if suffix not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"knowledge_suffix_not_supported:{suffix or 'none'}",
        )

    target_dir = container.rag_service.knowledge_directory()
    if target_dir.exists() and not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="knowledge_directory_is_file")
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    payload = await file.read()
    target_path.write_bytes(payload)

    stat = target_path.stat()
    relative_path = target_path.relative_to(target_dir).as_posix()
    try:
        container.rag_service.enqueue_reindex(relative_paths=[relative_path], kind="upload")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc
    rag_status = _build_knowledge_status(container)
    uploaded = next((item for item in rag_status.files if item.relative_path == relative_path), None)
    if uploaded is None:
        uploaded = KnowledgeFileItemDto(
            name=target_path.name,
            relative_path=relative_path,
            suffix=target_path.suffix.lower(),
            size_bytes=stat.st_size,
            updated_at=stat.st_mtime,
            status="pending",
        )
    return KnowledgeUploadResponseDto(
        file=uploaded,
        rag=rag_status,
    )


@router.delete("/files", status_code=204, response_class=Response)
def delete_knowledge_file(
    relative_path: str = Query(..., min_length=1),
    container: AppContainer = Depends(get_container),
    _: CurrentUser | None = Depends(require_admin),
) -> Response:
    target_dir = _require_knowledge_directory(container)
    target_path = _resolve_knowledge_relative_path(relative_path, target_dir=target_dir)

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="knowledge_file_not_found")

    suffix = target_path.suffix.lower()
    supported = set(container.rag_service.supported_suffixes())
    if suffix not in supported:
        raise HTTPException(status_code=400, detail=f"knowledge_suffix_not_supported:{suffix or 'none'}")

    target_path.unlink()

    try:
        container.rag_service.enqueue_reindex(relative_paths=[relative_path], kind="delete")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc

    return Response(status_code=204)


@router.post("/files/delete-batch", response_model=KnowledgeStatusDto)
def delete_knowledge_files_batch(
    payload: KnowledgeBatchDeleteRequest,
    container: AppContainer = Depends(get_container),
    _: CurrentUser | None = Depends(require_admin),
) -> KnowledgeStatusDto:
    target_dir = _require_knowledge_directory(container)
    relative_paths = [item.strip() for item in payload.relative_paths if item.strip()]
    if not relative_paths:
        raise HTTPException(status_code=400, detail="knowledge_relative_paths_required")

    supported = set(container.rag_service.supported_suffixes())
    validated_paths: list[Path] = []
    seen: set[str] = set()
    for relative_path in relative_paths:
        if relative_path in seen:
            continue
        seen.add(relative_path)
        target_path = _resolve_knowledge_relative_path(relative_path, target_dir=target_dir)
        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=404, detail=f"knowledge_file_not_found:{relative_path}")
        suffix = target_path.suffix.lower()
        if suffix not in supported:
            raise HTTPException(status_code=400, detail=f"knowledge_suffix_not_supported:{suffix or 'none'}")
        validated_paths.append(target_path)

    for target_path in validated_paths:
        target_path.unlink()

    try:
        container.rag_service.enqueue_reindex(
            relative_paths=[path.relative_to(target_dir).as_posix() for path in validated_paths],
            kind="delete",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc

    return _build_knowledge_status(container)
