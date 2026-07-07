// Generated from FastAPI OpenAPI components.
// Run `backend/.venv/bin/python backend/scripts/generate_http_contract.py` after editing backend DTOs.
// Do not edit by hand.

export type ArcadeGeoDto = {
  gcj02?: GeoPoint | null;
  wgs84?: GeoPoint | null;
  source: "catalog" | "geocode" | "client" | "route";
  precision: "exact" | "approx";
  [key: string]: unknown;
};

export type ArcadeDetailDto = {
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
  status?: number | string | null;
  type?: number | string | null;
  pay_type?: number | string | null;
  locked?: number | string | null;
  ea_status?: number | string | null;
  price?: string | number | null;
  start_time?: number | string | null;
  end_time?: number | string | null;
  fav_count?: number | null;
  updated_at?: string | null;
  arcade_count?: number;
  distance_m?: number | null;
  geo?: ArcadeGeoDto | null;
  comment?: string | null;
  url?: string | null;
  image_thumb?: Record<string, unknown> | null;
  events?: Array<Record<string, unknown>>;
  arcades?: Array<ArcadeTitleDto>;
  collab?: boolean | null;
  raw?: Record<string, unknown> | null;
  [key: string]: unknown;
};

export type ArcadeSummaryDto = {
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
  status?: number | string | null;
  type?: number | string | null;
  pay_type?: number | string | null;
  locked?: number | string | null;
  ea_status?: number | string | null;
  price?: string | number | null;
  start_time?: number | string | null;
  end_time?: number | string | null;
  fav_count?: number | null;
  updated_at?: string | null;
  arcade_count?: number;
  distance_m?: number | null;
  geo?: ArcadeGeoDto | null;
  [key: string]: unknown;
};

export type ArcadeTitleDto = {
  id?: number | null;
  title_id?: string | number | null;
  title_name?: string | null;
  quantity?: number | null;
  version?: string | null;
  coin?: string | number | null;
  eacoin?: string | number | null;
  comment?: string | null;
  [key: string]: unknown;
};

export type Body_chat_with_upload_api_chat_upload_post = {
  session_id?: string | null;
  client_id?: string | null;
  idempotency_key?: string | null;
  message?: string | null;
  intent?: string | null;
  shop_id?: string | null;
  location?: string | null;
  keyword?: string | null;
  province_code?: string | null;
  city_code?: string | null;
  county_code?: string | null;
  page_size?: string | null;
  files?: Array<string>;
  [key: string]: unknown;
};

export type Body_dispatch_chat_session_with_upload_api_chat_sessions_upload_post = {
  session_id?: string | null;
  client_id?: string | null;
  idempotency_key?: string | null;
  message?: string | null;
  intent?: string | null;
  shop_id?: string | null;
  location?: string | null;
  keyword?: string | null;
  province_code?: string | null;
  city_code?: string | null;
  county_code?: string | null;
  page_size?: string | null;
  files?: Array<string>;
  [key: string]: unknown;
};

export type Body_upload_knowledge_file_api_knowledge_upload_post = {
  file: string;
  [key: string]: unknown;
};

export type ChatAttachmentDto = {
  name: string;
  mime_type: string;
  size_bytes?: number;
  kind: "image" | "document";
  preview_text?: string | null;
  extracted_text?: string | null;
  image_data_url?: string | null;
  [key: string]: unknown;
};

export type ChatHistoryTurnDto = {
  role: "user" | "assistant" | "tool";
  content: string;
  name?: string | null;
  call_id?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
  [key: string]: unknown;
};

export type ChatRequest = {
  session_id?: string | null;
  client_id?: string | null;
  idempotency_key?: string | null;
  message?: string;
  intent?: "search_nearby" | "navigate" | "search" | null;
  shop_id?: number | null;
  location?: ClientLocationContext | null;
  keyword?: string | null;
  province_code?: string | null;
  city_code?: string | null;
  county_code?: string | null;
  page_size?: number;
  attachments?: Array<ChatAttachmentDto>;
  [key: string]: unknown;
};

export type ChatResponse = {
  session_id: string;
  intent: "search_nearby" | "navigate" | "search";
  reply: string;
  shops?: Array<ArcadeSummaryDto>;
  route?: RouteSummaryDto | null;
  map_artifact?: MapArtifactDto | null;
  [key: string]: unknown;
};

export type ChatSessionDetailDto = {
  session_id: string;
  intent: "search_nearby" | "navigate" | "search";
  active_subagent: string;
  status: "idle" | "running" | "completed" | "failed";
  run_status?: "idle" | "running" | "completed" | "failed";
  idempotency_key?: string | null;
  last_stream_offset?: number;
  last_error?: string | null;
  reply?: string | null;
  shops?: Array<ArcadeSummaryDto>;
  route?: RouteSummaryDto | null;
  client_location?: ClientLocationContext | null;
  destination?: ArcadeSummaryDto | null;
  view_payload?: MapViewPayloadDto | null;
  map_artifact?: MapArtifactDto | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
  turns?: Array<ChatHistoryTurnDto>;
  [key: string]: unknown;
};

export type ChatSessionDispatchDto = {
  session_id: string;
  status: "idle" | "running" | "completed" | "failed";
  run_status?: "idle" | "running" | "completed" | "failed";
  idempotency_key?: string | null;
  last_stream_offset?: number;
  [key: string]: unknown;
};

export type ChatSessionSummaryDto = {
  session_id: string;
  title: string;
  preview?: string | null;
  intent: "search_nearby" | "navigate" | "search";
  status: "idle" | "running" | "completed" | "failed";
  turn_count: number;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
};

export type ClientLocationContext = {
  lng: number;
  lat: number;
  accuracy_m?: number | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  township?: string | null;
  adcode?: string | null;
  formatted_address?: string | null;
  region_text?: string | null;
  [key: string]: unknown;
};

export type GeoPoint = {
  lng: number;
  lat: number;
  coord_system?: "gcj02" | "wgs84";
  source?: "catalog" | "geocode" | "client" | "route";
  precision?: "exact" | "approx";
  [key: string]: unknown;
};

export type HTTPValidationError = {
  detail?: Array<ValidationError>;
  [key: string]: unknown;
};

export type KnowledgeArcadeCandidateDto = {
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
  geo?: ArcadeGeoDto | null;
  [key: string]: unknown;
};

export type KnowledgeBatchDeleteRequest = {
  relative_paths?: Array<string>;
  [key: string]: unknown;
};

export type KnowledgeFileItemDto = {
  name: string;
  relative_path: string;
  suffix: string;
  size_bytes: number;
  updated_at: number;
  status?: "pending" | "indexing" | "ready" | "failed";
  chunk_count?: number;
  content_hash?: string | null;
  indexed_at?: number | null;
  error?: string | null;
  job_id?: string | null;
  [key: string]: unknown;
};

export type KnowledgeLookupHitDto = {
  title?: string | null;
  source_uri?: string | null;
  source_type?: string | null;
  score?: number | null;
  snippet?: string | null;
  [key: string]: unknown;
};

export type KnowledgeLookupResponseDto = {
  query: string;
  status: string;
  total_hits?: number;
  hits?: Array<KnowledgeLookupHitDto>;
  arcade_candidates?: Array<KnowledgeArcadeCandidateDto>;
  [key: string]: unknown;
};

export type KnowledgeRetryRequest = {
  relative_path: string;
  [key: string]: unknown;
};

export type KnowledgeStatusDto = {
  directory: string;
  enabled: boolean;
  source_exists: boolean;
  source_is_dir: boolean;
  supported_suffixes: Array<string>;
  semantic_chunking_enabled: boolean;
  reranker_enabled: boolean;
  hybrid_search_enabled: boolean;
  index_ready: boolean;
  chunk_count: number;
  pending_count?: number;
  indexing_count?: number;
  ready_count?: number;
  failed_count?: number;
  job_count?: number;
  active_job_id?: string | null;
  load_error?: string | null;
  files?: Array<KnowledgeFileItemDto>;
  [key: string]: unknown;
};

export type KnowledgeUploadResponseDto = {
  file: KnowledgeFileItemDto;
  rag: KnowledgeStatusDto;
  [key: string]: unknown;
};

export type MapArtifactDto = {
  schema_version?: number;
  scene: "agent_candidates" | "agent_route";
  shops?: Array<ArcadeSummaryDto>;
  route?: RouteSummaryDto | null;
  client_location?: ClientLocationContext | null;
  destination?: ArcadeSummaryDto | null;
  view_payload?: MapViewPayloadDto | null;
  [key: string]: unknown;
};

export type MapViewPayloadDto = {
  schema_version?: number;
  scene: "agent_candidates" | "agent_route";
  title?: string | null;
  [key: string]: unknown;
};

export type PagedArcadesDto = {
  items: Array<ArcadeSummaryDto>;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  [key: string]: unknown;
};

export type RegionItemDto = {
  code: string;
  name: string;
  [key: string]: unknown;
};

export type ReverseGeocodeRequest = {
  lng: number;
  lat: number;
  accuracy_m?: number | null;
  [key: string]: unknown;
};

export type ReverseGeocodeResponse = {
  lng: number;
  lat: number;
  accuracy_m?: number | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
  township?: string | null;
  adcode?: string | null;
  formatted_address?: string | null;
  region_text?: string | null;
  resolved?: boolean;
  [key: string]: unknown;
};

export type RouteSummaryDto = {
  schema_version?: number;
  provider: "amap" | "google" | "none";
  mode: string;
  distance_m?: number | null;
  duration_s?: number | null;
  origin?: GeoPoint | null;
  destination?: GeoPoint | null;
  polyline?: Array<GeoPoint>;
  hint?: string | null;
  [key: string]: unknown;
};

export type ValidationError = {
  loc: Array<string | number>;
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
  [key: string]: unknown;
};

