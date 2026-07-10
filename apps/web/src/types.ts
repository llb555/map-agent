import type {
  ArcadeDetailDto,
  ArcadeGeoDto,
  ArcadeSummaryDto,
  ArcadeTitleDto,
  ChatAttachmentDto,
  ChatHistoryTurnDto,
  ChatRequest as GeneratedChatRequest,
  ChatResponse as GeneratedChatResponse,
  ChatSessionDetailDto,
  ChatSessionDispatchDto,
  ChatSessionSummaryDto,
  ClientLocationContext as GeneratedClientLocationContext,
  GeoPoint as GeneratedGeoPoint,
  KnowledgeArcadeCandidateDto,
  KnowledgeFileItemDto,
  KnowledgeLookupHitDto,
  KnowledgeLookupResponseDto,
  KnowledgeStatusDto,
  KnowledgeUploadResponseDto,
  PagedArcadesDto,
  RegionItemDto,
  ReverseGeocodeRequest as GeneratedReverseGeocodeRequest,
  ReverseGeocodeResponse as GeneratedReverseGeocodeResponse,
  RouteSummaryDto
} from "./generated/httpContract";

export type RegionItem = RegionItemDto;

export type ViewMode = "chat" | "arcades" | "knowledge";

export type ArcadeSortBy = "default" | "updated_at" | "source_id" | "arcade_count" | "title_quantity" | "distance";
export type SortOrder = "asc" | "desc";
export type CoordSystem = "gcj02" | "wgs84";
export type GeoSource = "catalog" | "geocode" | "client" | "route";
export type GeoPrecision = "exact" | "approx";

export type GeoPoint = Omit<GeneratedGeoPoint, "coord_system" | "source" | "precision"> & {
  lng: number;
  lat: number;
  coord_system: CoordSystem;
  source: GeoSource;
  precision: GeoPrecision;
};

export type ArcadeGeo = Omit<ArcadeGeoDto, "gcj02" | "wgs84" | "source" | "precision"> & {
  gcj02?: GeoPoint | null;
  wgs84?: GeoPoint | null;
  source: GeoSource;
  precision: GeoPrecision;
};

export type ArcadeSummary = Omit<ArcadeSummaryDto, "arcade_count" | "geo"> & {
  source: string;
  source_id: number;
  source_url: string;
  name: string;
  name_pinyin?: string | null;
  address?: string | null;
  transport?: string | null;
  province_code?: string | null;
  province_name?: string | null;
  city_code?: string | null;
  city_name?: string | null;
  county_code?: string | null;
  county_name?: string | null;
  status?: string | number | null;
  type?: string | number | null;
  pay_type?: string | number | null;
  locked?: string | number | null;
  ea_status?: string | number | null;
  price?: string | number | null;
  start_time?: string | number | null;
  end_time?: string | number | null;
  fav_count?: number | null;
  updated_at?: string | null;
  arcade_count: number;
  distance_m?: number | null;
  geo?: ArcadeGeo | null;
};

export type ArcadeTitle = ArcadeTitleDto;

export type ArcadeDetail = ArcadeSummary & Omit<ArcadeDetailDto, "arcades" | "events" | "geo" | "arcade_count"> & {
  comment?: string | null;
  url?: string | null;
  image_thumb?: Record<string, unknown> | null;
  events: Array<Record<string, unknown>>;
  arcades: ArcadeTitle[];
  collab?: boolean | null;
};

export type PagedArcades = Omit<PagedArcadesDto, "items"> & {
  items: ArcadeSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type IntentType = "search" | "search_nearby" | "navigate";
export type ChatSessionStatus = "idle" | "running" | "completed" | "failed";

export type ClientLocationContext = GeneratedClientLocationContext;

export type ReverseGeocodeRequest = GeneratedReverseGeocodeRequest;

export type ReverseGeocodeResponse = GeneratedReverseGeocodeResponse & ClientLocationContext & {
  resolved: boolean;
};

export type ChatRequest = GeneratedChatRequest & {
  session_id?: string;
  client_id?: string;
  idempotency_key?: string;
  message: string;
  intent?: IntentType;
  shop_id?: number;
  location?: ClientLocationContext;
  keyword?: string;
  province_code?: string;
  city_code?: string;
  county_code?: string;
  page_size?: number;
  attachments?: ChatAttachment[];
};

export type ChatAttachment = ChatAttachmentDto & {
  name: string;
  mime_type: string;
  size_bytes: number;
  kind: "image" | "document";
  preview_text?: string | null;
  image_data_url?: string | null;
};

export type RouteSummary = Omit<RouteSummaryDto, "origin" | "destination" | "polyline"> & {
  schema_version?: number;
  provider: "amap" | "google" | "none";
  mode: string;
  distance_m?: number | null;
  duration_s?: number | null;
  origin?: GeoPoint | null;
  destination?: GeoPoint | null;
  polyline: GeoPoint[];
  hint?: string | null;
};

export type AgentMapScene = "agent_candidates" | "agent_route";

export type MapViewPayload = {
  schema_version?: number;
  version?: number;
  scene?: AgentMapScene;
  title?: string | null;
  [key: string]: unknown;
};

export type ChatMapArtifacts = {
  schema_version: number;
  scene: AgentMapScene;
  shops: ArcadeSummary[];
  route?: RouteSummary | null;
  client_location?: ClientLocationContext | null;
  destination?: ArcadeSummary | null;
  view_payload?: MapViewPayload | null;
  route_pending?: boolean;
};

export type ChatResponse = Omit<GeneratedChatResponse, "shops" | "route" | "map_artifact"> & {
  session_id: string;
  intent: IntentType;
  reply: string;
  shops: ArcadeSummary[];
  route?: RouteSummary | null;
  map_artifact?: ChatMapArtifacts | null;
};

export type ChatSessionDispatch = Omit<ChatSessionDispatchDto, "status" | "run_status" | "last_stream_offset"> & {
  session_id: string;
  status: ChatSessionStatus;
  run_status: ChatSessionStatus;
  idempotency_key?: string | null;
  last_stream_offset: number;
};

export type ChatHistoryTurn = ChatHistoryTurnDto & {
  role: "user" | "assistant" | "tool";
  content: string;
  name?: string | null;
  call_id?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
};

export type ChatSessionSummary = ChatSessionSummaryDto & {
  session_id: string;
  title: string;
  preview?: string | null;
  intent: IntentType;
  status: ChatSessionStatus;
  turn_count: number;
  created_at: string;
  updated_at: string;
};

export type ChatSessionDetail = Omit<
  ChatSessionDetailDto,
  "status" | "run_status" | "shops" | "route" | "client_location" | "destination" | "view_payload" | "map_artifact" | "turns" | "last_stream_offset"
> & {
  session_id: string;
  intent: IntentType;
  active_subagent: string;
  status: ChatSessionStatus;
  run_status: ChatSessionStatus;
  idempotency_key?: string | null;
  last_stream_offset: number;
  last_error?: string | null;
  reply?: string | null;
  shops: ArcadeSummary[];
  route?: RouteSummary | null;
  client_location?: ClientLocationContext | null;
  destination?: ArcadeSummary | null;
  view_payload?: MapViewPayload | null;
  map_artifact?: ChatMapArtifacts | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
  turns: ChatHistoryTurn[];
};

export type KnowledgeFileItem = Omit<KnowledgeFileItemDto, "status" | "chunk_count"> & {
  name: string;
  relative_path: string;
  suffix: string;
  size_bytes: number;
  updated_at: number;
  status: "pending" | "indexing" | "ready" | "failed";
  chunk_count: number;
  content_hash?: string | null;
  indexed_at?: number | null;
  error?: string | null;
  job_id?: string | null;
};

export type KnowledgeStatus = Omit<
  KnowledgeStatusDto,
  "pending_count" | "indexing_count" | "ready_count" | "failed_count" | "job_count" | "files"
> & {
  directory: string;
  enabled: boolean;
  source_exists: boolean;
  source_is_dir: boolean;
  supported_suffixes: string[];
  semantic_chunking_enabled: boolean;
  reranker_enabled: boolean;
  hybrid_search_enabled: boolean;
  index_ready: boolean;
  chunk_count: number;
  pending_count: number;
  indexing_count: number;
  ready_count: number;
  failed_count: number;
  job_count: number;
  active_job_id?: string | null;
  load_error?: string | null;
  files: KnowledgeFileItem[];
};

export type KnowledgeUploadResponse = Omit<KnowledgeUploadResponseDto, "file" | "rag"> & {
  file: KnowledgeFileItem;
  rag: KnowledgeStatus;
};

export type CurrentUser = {
  id: string;
  email: string | null;
  role: "anonymous" | "user" | "contributor" | "admin";
};

export type KnowledgeSubmission = {
  id: string;
  owner_user_id: string;
  owner_email: string | null;
  original_filename: string;
  suffix: string;
  size_bytes: number;
  sha256: string;
  title: string | null;
  description: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  published_relative_path: string | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeLookupHit = KnowledgeLookupHitDto;

export type KnowledgeArcadeCandidate = Omit<KnowledgeArcadeCandidateDto, "geo"> & {
  id: string;
  name: string;
  address?: string | null;
  region_text?: string | null;
  province_name?: string | null;
  city_name?: string | null;
  county_name?: string | null;
  transport?: string | null;
  source_uri?: string | null;
  source_type?: string | null;
  score?: number | null;
  geo?: ArcadeGeo | null;
};

export type KnowledgeLookupResponse = Omit<KnowledgeLookupResponseDto, "total_hits" | "hits" | "arcade_candidates"> & {
  query: string;
  status: string;
  total_hits: number;
  hits: KnowledgeLookupHit[];
  arcade_candidates: KnowledgeArcadeCandidate[];
};

export type {
  ChatStreamEnvelope,
  ChatStreamEventName
} from "./generated/chatStreamContract";
