"""Protocol layer: request/response DTOs shared by API and orchestrator modules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


IntentType = Literal["search_nearby", "navigate", "search"]
ChatRoleType = Literal["user", "assistant", "tool"]
ProviderType = Literal["amap", "google", "none"]
ChatSessionStatusType = Literal["idle", "running", "completed", "failed"]
CoordSystemType = Literal["gcj02", "wgs84"]
GeoSourceType = Literal["catalog", "geocode", "client", "route"]
GeoPrecisionType = Literal["exact", "approx"]


class Location(BaseModel):
    """Client-side location DTO."""

    lng: float = Field(..., description="Longitude in WGS84.")
    lat: float = Field(..., description="Latitude in WGS84.")


class GeoPoint(BaseModel):
    """Public geo payload with explicit coordinate-system semantics."""

    lng: float
    lat: float
    coord_system: CoordSystemType = "gcj02"
    source: GeoSourceType = "route"
    precision: GeoPrecisionType = "approx"

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_mapping(cls, raw: object) -> object:
        if not isinstance(raw, dict):
            return raw
        if raw.get("lng") is None or raw.get("lat") is None:
            return raw
        payload = dict(raw)
        payload.setdefault("coord_system", "gcj02")
        payload.setdefault("source", "route")
        payload.setdefault("precision", "approx")
        return payload


class ArcadeGeoDto(BaseModel):
    """Per-shop geo payload with GCJ02 and optional WGS84 coordinates."""

    gcj02: GeoPoint | None = None
    wgs84: GeoPoint | None = None
    source: GeoSourceType
    precision: GeoPrecisionType


class ClientLocationContext(BaseModel):
    """Browser geolocation plus optional reverse-geocoded region context."""

    lng: float = Field(..., description="Longitude in WGS84.")
    lat: float = Field(..., description="Latitude in WGS84.")
    accuracy_m: float | None = Field(default=None, ge=0, description="Browser-reported accuracy in meters.")
    province: str | None = None
    city: str | None = None
    district: str | None = None
    township: str | None = None
    adcode: str | None = None
    formatted_address: str | None = None
    region_text: str | None = None


class ReverseGeocodeRequest(BaseModel):
    """Lookup request for browser coordinates."""

    lng: float = Field(..., description="Longitude in WGS84.")
    lat: float = Field(..., description="Latitude in WGS84.")
    accuracy_m: float | None = Field(default=None, ge=0, description="Browser-reported accuracy in meters.")


class ReverseGeocodeResponse(ClientLocationContext):
    """Reverse-geocode result returned to the browser."""

    resolved: bool = False


class ArcadeTitleDto(BaseModel):
    """Title machine item under a single shop."""

    id: int | None = None
    title_id: str | int | None = None
    title_name: str | None = None
    quantity: int | None = None
    version: str | None = None
    coin: str | int | float | None = None
    eacoin: str | int | float | None = None
    comment: str | None = None


class ArcadeShopSummaryDto(BaseModel):
    """Summary representation for listing/search APIs."""

    source: str
    source_id: int
    source_url: str
    name: str
    name_pinyin: str | None = None
    address: str | None = None
    transport: str | None = None
    province_code: str | None = None
    province_name: str | None = None
    city_code: str | None = None
    city_name: str | None = None
    county_code: str | None = None
    county_name: str | None = None
    status: int | str | None = None
    type: int | str | None = None
    pay_type: int | str | None = None
    locked: int | str | None = None
    ea_status: int | str | None = None
    price: str | int | float | None = None
    start_time: int | str | None = None
    end_time: int | str | None = None
    fav_count: int | None = None
    updated_at: str | None = None
    arcade_count: int = 0
    distance_m: int | None = None
    geo: ArcadeGeoDto | None = None


class ArcadeShopDetailDto(ArcadeShopSummaryDto):
    """Detailed shop payload including titles/raw optional metadata."""

    comment: str | None = None
    url: str | None = None
    image_thumb: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    arcades: list[ArcadeTitleDto] = Field(default_factory=list)
    collab: bool | None = None
    raw: dict[str, Any] | None = None


class PagedArcadeResponse(BaseModel):
    """Paginated list response contract."""

    items: list[ArcadeShopSummaryDto]
    page: int
    page_size: int
    total: int
    total_pages: int


class RegionItemDto(BaseModel):
    """Standardized region item for province/city/county endpoints."""

    code: str
    name: str


class KnowledgeFileItemDto(BaseModel):
    """One knowledge source file currently visible to RAG."""

    name: str
    relative_path: str
    suffix: str
    size_bytes: int
    updated_at: float


class KnowledgeStatusDto(BaseModel):
    """Knowledge base management/status payload."""

    directory: str
    enabled: bool
    source_exists: bool
    source_is_dir: bool
    supported_suffixes: list[str]
    semantic_chunking_enabled: bool
    reranker_enabled: bool
    hybrid_search_enabled: bool
    index_ready: bool
    chunk_count: int
    load_error: str | None = None
    files: list[KnowledgeFileItemDto] = Field(default_factory=list)


class KnowledgeUploadResponseDto(BaseModel):
    """Upload result for one knowledge file."""

    file: KnowledgeFileItemDto
    rag: KnowledgeStatusDto


class KnowledgeLookupHitDto(BaseModel):
    """One lightweight knowledge hit for browser-side fallback messaging."""

    title: str | None = None
    source_uri: str | None = None
    source_type: str | None = None
    score: float | None = None
    snippet: str | None = None


class KnowledgeArcadeCandidateDto(BaseModel):
    """Structured arcade candidate parsed from a knowledge-base hit."""

    id: str
    name: str
    address: str | None = None
    region_text: str | None = None
    province_name: str | None = None
    city_name: str | None = None
    county_name: str | None = None
    transport: str | None = None
    source_uri: str | None = None
    source_type: str | None = None
    score: float | None = None
    geo: ArcadeGeoDto | None = None


class KnowledgeLookupResponseDto(BaseModel):
    """Knowledge lookup response used by the arcade browser fallback flow."""

    query: str
    status: str
    total_hits: int = 0
    hits: list[KnowledgeLookupHitDto] = Field(default_factory=list)
    arcade_candidates: list[KnowledgeArcadeCandidateDto] = Field(default_factory=list)



class RouteSummaryDto(BaseModel):
    """Route plan payload returned by navigation flow."""

    provider: ProviderType
    mode: str
    distance_m: int | None = None
    duration_s: int | None = None
    origin: GeoPoint | None = None
    destination: GeoPoint | None = None
    polyline: list[GeoPoint] = Field(default_factory=list)
    hint: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_route(cls, raw: object) -> object:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        polyline = payload.get("polyline")
        if isinstance(polyline, list) and polyline:
            first = polyline[0]
            last = polyline[-1]
            payload.setdefault("origin", first)
            payload.setdefault("destination", last)
        return payload


class ChatAttachmentDto(BaseModel):
    """One uploaded attachment accompanying a chat turn."""

    name: str = Field(..., min_length=1, max_length=256)
    mime_type: str = Field(..., min_length=1, max_length=128)
    size_bytes: int = Field(default=0, ge=0, le=10 * 1024 * 1024)
    kind: Literal["image", "document"]
    preview_text: str | None = Field(default=None, max_length=2000)
    extracted_text: str | None = Field(default=None, exclude=True, max_length=12000)
    image_data_url: str | None = Field(default=None, exclude=True, max_length=16 * 1024 * 1024)


class ChatRequest(BaseModel):
    """Chat entrypoint request used by the orchestrator."""

    session_id: str | None = None
    client_id: str | None = Field(default=None, min_length=1, max_length=128)
    message: str = Field(default="", max_length=2000)
    intent: IntentType | None = None
    shop_id: int | None = None
    location: ClientLocationContext | None = None
    keyword: str | None = None
    province_code: str | None = None
    city_code: str | None = None
    county_code: str | None = None
    page_size: int = Field(default=5, ge=1, le=50)
    attachments: list[ChatAttachmentDto] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_message_or_attachments(self) -> "ChatRequest":
        if self.message.strip() or self.attachments:
            return self
        raise ValueError("message_or_attachments_required")


class ChatResponse(BaseModel):
    """Chat entrypoint response DTO."""

    session_id: str
    intent: IntentType
    reply: str
    shops: list[ArcadeShopSummaryDto] = Field(default_factory=list)
    route: RouteSummaryDto | None = None


class ChatSessionDispatchDto(BaseModel):
    """Accepted async chat dispatch response."""

    session_id: str
    status: ChatSessionStatusType


class ChatHistoryTurnDto(BaseModel):
    """Persisted chat history turn for one session."""

    role: ChatRoleType
    content: str
    name: str | None = None
    call_id: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str


class ChatSessionSummaryDto(BaseModel):
    """Session summary card shown in sidebar/history list."""

    session_id: str
    title: str
    preview: str | None = None
    intent: IntentType
    status: ChatSessionStatusType
    turn_count: int
    created_at: str
    updated_at: str


class ChatSessionDetailDto(BaseModel):
    """Full session payload used to restore message history in UI."""

    session_id: str
    intent: IntentType
    active_subagent: str
    status: ChatSessionStatusType
    last_error: str | None = None
    reply: str | None = None
    shops: list[ArcadeShopSummaryDto] = Field(default_factory=list)
    route: RouteSummaryDto | None = None
    client_location: ClientLocationContext | None = None
    destination: ArcadeShopSummaryDto | None = None
    view_payload: dict[str, Any] | None = None
    turn_count: int
    created_at: str
    updated_at: str
    turns: list[ChatHistoryTurnDto] = Field(default_factory=list)
