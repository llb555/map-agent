import type {
  ArcadeDetail,
  ArcadeSortBy,
  ChatAttachment,
  ChatRequest,
  ChatSessionDispatch,
  ChatResponse,
  ChatSessionDetail,
  ChatSessionSummary,
  KnowledgeLookupResponse,
  KnowledgeStatus,
  KnowledgeUploadResponse,
  ReverseGeocodeRequest,
  ReverseGeocodeResponse,
  PagedArcades,
  RegionItem,
  SortOrder
} from "../types";

function resolveApiBase(): string {
  const fallback = typeof window !== "undefined" ? window.location.origin : "http://localhost:8000";
  const configured = import.meta.env.VITE_API_BASE?.trim();
  if (!configured) {
    return fallback;
  }
  if (/^https?:\/\//i.test(configured) || configured.startsWith("/")) {
    return new URL(configured, fallback).toString();
  }
  return `http://${configured}`;
}

const API_BASE = resolveApiBase();

function buildUrl(path: string, query?: Record<string, string | number | boolean | undefined | null>): string {
  const url = new URL(path, API_BASE);
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && `${value}`.length > 0) {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

async function parseJsonResponse<T>(resp: Response, requestLabel: string): Promise<T> {
  const contentType = resp.headers.get("content-type")?.toLowerCase() ?? "";
  const text = await resp.text();

  if (!resp.ok) {
    const detail = text.trim().slice(0, 180);
    throw new Error(`HTTP ${resp.status}: ${requestLabel}${detail ? ` - ${detail}` : ""}`);
  }

  if (!contentType.includes("application/json")) {
    const preview = text.trim().slice(0, 120);
    throw new Error(
      `Expected JSON from ${requestLabel}, got ${contentType || "unknown content type"}${preview ? ` - ${preview}` : ""}`
    );
  }

  try {
    return JSON.parse(text) as T;
  } catch (error) {
    const preview = text.trim().slice(0, 120);
    throw new Error(
      `Invalid JSON from ${requestLabel}${preview ? ` - ${preview}` : ""}${error instanceof Error ? ` (${error.message})` : ""}`
    );
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  return parseJsonResponse<T>(resp, url);
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const resp = await fetch(buildUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  return parseJsonResponse<T>(resp, path);
}

async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const resp = await fetch(buildUrl(path), {
    method: "POST",
    body: formData
  });
  return parseJsonResponse<T>(resp, path);
}

async function deleteJson(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>
): Promise<void> {
  const resp = await fetch(buildUrl(path, query), { method: "DELETE" });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${path}`);
  }
}

export async function listArcades(params: {
  keyword?: string;
  shop_name?: string;
  title_name?: string;
  province_code?: string;
  city_code?: string;
  county_code?: string;
  has_arcades?: boolean;
  sort_by?: ArcadeSortBy;
  sort_order?: SortOrder;
  sort_title_name?: string;
  origin_lng?: number;
  origin_lat?: number;
  origin_coord_system?: "wgs84" | "gcj02";
  page?: number;
  page_size?: number;
}): Promise<PagedArcades> {
  return fetchJson<PagedArcades>(buildUrl("/api/arcades", params));
}

export async function getArcadeDetail(sourceId: number): Promise<ArcadeDetail> {
  return fetchJson<ArcadeDetail>(buildUrl(`/api/arcades/${sourceId}`));
}

export async function listProvinces(): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/provinces"));
}

export async function listCities(provinceCode: string): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/cities", { province_code: provinceCode }));
}

export async function listCounties(cityCode: string): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/counties", { city_code: cityCode }));
}

export async function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  return postJson<ChatResponse>("/api/chat", payload);
}

export async function dispatchChatSession(payload: ChatRequest): Promise<ChatSessionDispatch> {
  return postJson<ChatSessionDispatch>("/api/chat/sessions", payload);
}

export async function dispatchChatSessionWithUploads(payload: ChatRequest, files: File[]): Promise<ChatSessionDispatch> {
  const formData = new FormData();
  formData.append("session_id", payload.session_id || "");
  formData.append("client_id", payload.client_id || "");
  formData.append("message", payload.message || "");
  formData.append("page_size", String(payload.page_size || 5));
  if (payload.intent) {
    formData.append("intent", payload.intent);
  }
  if (payload.shop_id != null) {
    formData.append("shop_id", String(payload.shop_id));
  }
  if (payload.keyword) {
    formData.append("keyword", payload.keyword);
  }
  if (payload.province_code) {
    formData.append("province_code", payload.province_code);
  }
  if (payload.city_code) {
    formData.append("city_code", payload.city_code);
  }
  if (payload.county_code) {
    formData.append("county_code", payload.county_code);
  }
  if (payload.location) {
    formData.append("location", JSON.stringify(payload.location));
  }
  files.forEach((file) => {
    formData.append("files", file);
  });
  return postFormData<ChatSessionDispatch>("/api/chat/sessions/upload", formData);
}

export function buildChatStreamUrl(sessionId: string, lastEventId?: number, clientId?: string): string {
  return buildUrl(`/api/stream/${encodeURIComponent(sessionId)}`, {
    client_id: clientId,
    last_event_id: typeof lastEventId === "number" ? lastEventId : undefined
  });
}

export async function listChatSessions(limit = 40, clientId?: string): Promise<ChatSessionSummary[]> {
  return fetchJson<ChatSessionSummary[]>(buildUrl("/api/chat/sessions", { limit, client_id: clientId }));
}

export async function getChatSession(sessionId: string, clientId?: string): Promise<ChatSessionDetail> {
  return fetchJson<ChatSessionDetail>(
    buildUrl(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { client_id: clientId })
  );
}

export async function deleteChatSession(sessionId: string, clientId?: string): Promise<void> {
  return deleteJson(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { client_id: clientId });
}

export async function reverseGeocodeLocation(
  payload: ReverseGeocodeRequest
): Promise<ReverseGeocodeResponse> {
  return postJson<ReverseGeocodeResponse>("/api/location/reverse-geocode", payload);
}

export async function getKnowledgeStatus(): Promise<KnowledgeStatus> {
  return fetchJson<KnowledgeStatus>(buildUrl("/api/knowledge/status"));
}

export async function lookupKnowledge(query: string, topK = 3): Promise<KnowledgeLookupResponse> {
  return fetchJson<KnowledgeLookupResponse>(buildUrl("/api/knowledge/lookup", { q: query, top_k: topK }));
}

export async function reindexKnowledge(): Promise<KnowledgeStatus> {
  return postJson<KnowledgeStatus>("/api/knowledge/reindex", {});
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return postFormData<KnowledgeUploadResponse>("/api/knowledge/upload", formData);
}

export async function deleteKnowledgeFile(relativePath: string): Promise<void> {
  return deleteJson("/api/knowledge/files", { relative_path: relativePath });
}

export async function deleteKnowledgeFilesBatch(relativePaths: string[]): Promise<KnowledgeStatus> {
  return postJson<KnowledgeStatus>("/api/knowledge/files/delete-batch", { relative_paths: relativePaths });
}
