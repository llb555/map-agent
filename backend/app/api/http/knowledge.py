"""HTTP API layer: knowledge base upload and reindex management."""

from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_container
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


@router.post("/reindex", response_model=KnowledgeStatusDto)
def reindex_knowledge(container: AppContainer = Depends(get_container)) -> KnowledgeStatusDto:
    try:
        container.rag_service.rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc
    return _build_knowledge_status(container)


@router.post("/upload", response_model=KnowledgeUploadResponseDto)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
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

    try:
        rag_status = container.rag_service.rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc

    stat = target_path.stat()
    uploaded = KnowledgeFileItemDto(
        name=target_path.name,
        relative_path=target_path.relative_to(target_dir).as_posix(),
        suffix=target_path.suffix.lower(),
        size_bytes=stat.st_size,
        updated_at=stat.st_mtime,
    )
    return KnowledgeUploadResponseDto(
        file=uploaded,
        rag=KnowledgeStatusDto(
            directory=str(container.rag_service.knowledge_directory()),
            enabled=bool(rag_status.get("enabled")),
            source_exists=bool(rag_status.get("source_exists")),
            source_is_dir=bool(rag_status.get("source_is_dir")),
            supported_suffixes=list(rag_status.get("supported_suffixes") or []),
            semantic_chunking_enabled=bool(rag_status.get("semantic_chunking_enabled")),
            reranker_enabled=bool(rag_status.get("reranker_enabled")),
            hybrid_search_enabled=bool(rag_status.get("hybrid_search_enabled")),
            index_ready=bool(rag_status.get("index_ready")),
            chunk_count=int(rag_status.get("chunk_count") or 0),
            load_error=str(rag_status.get("load_error")) if rag_status.get("load_error") is not None else None,
            files=[KnowledgeFileItemDto(**item) for item in container.rag_service.list_source_files()],
        ),
    )


@router.delete("/files", status_code=204, response_class=Response)
def delete_knowledge_file(
    relative_path: str = Query(..., min_length=1),
    container: AppContainer = Depends(get_container),
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
        container.rag_service.rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc

    return Response(status_code=204)


@router.post("/files/delete-batch", response_model=KnowledgeStatusDto)
def delete_knowledge_files_batch(
    payload: KnowledgeBatchDeleteRequest,
    container: AppContainer = Depends(get_container),
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
        container.rag_service.rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip() or type(exc).__name__) from exc

    return _build_knowledge_status(container)
