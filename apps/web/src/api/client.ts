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
  KnowledgeSubmission,
  KnowledgeArcadeCandidate,
  KnowledgeArcadePromotionResponse,
  CurrentUser,
  ReverseGeocodeRequest,
  ReverseGeocodeResponse,
  PagedArcades,
  RegionItem,
  SortOrder
} from "../types";
import { fetchWithAuth } from "../lib/auth";

export type RequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
  traceId?: string;
};

export class ApiRequestError extends Error {
  status: number;
  requestLabel: string;
  traceId: string | null;
  detail: string;

  constructor({
    status,
    requestLabel,
    traceId,
    detail
  }: {
    status: number;
    requestLabel: string;
    traceId: string | null;
    detail: string;
  }) {
    super(`HTTP ${status}: ${requestLabel}${detail ? ` - ${detail}` : ""}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.requestLabel = requestLabel;
    this.traceId = traceId;
    this.detail = detail;
  }
}

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
const DEFAULT_REQUEST_TIMEOUT_MS = 20_000;

function makeTraceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `web_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  }
  return `web_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function makeRequestSignal(options: RequestOptions = {}): {
  signal?: AbortSignal;
  traceId: string;
  cleanup: () => void;
} {
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const traceId = options.traceId || makeTraceId();
  if (!timeoutMs || timeoutMs <= 0) {
    return { signal: options.signal, traceId, cleanup: () => undefined };
  }

  const controller = new AbortController();
  const onAbort = () => controller.abort(options.signal?.reason);
  const timer = setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs);
  if (options.signal) {
    if (options.signal.aborted) {
      onAbort();
    } else {
      options.signal.addEventListener("abort", onAbort, { once: true });
    }
  }

  return {
    signal: controller.signal,
    traceId,
    cleanup: () => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    }
  };
}

function requestHeaders(options: RequestOptions = {}, traceId?: string): HeadersInit {
  return {
    ...(traceId || options.traceId ? { "X-Request-Trace-Id": traceId || options.traceId || "" } : {})
  };
}

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
    throw new ApiRequestError({
      status: resp.status,
      requestLabel,
      traceId: resp.headers.get("x-request-trace-id"),
      detail
    });
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

async function fetchJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const request = makeRequestSignal(options);
  try {
    const resp = await fetchWithAuth(url, {
      signal: request.signal,
      headers: requestHeaders(options, request.traceId)
    });
    return parseJsonResponse<T>(resp, url);
  } finally {
    request.cleanup();
  }
}

async function postJson<T>(path: string, payload: unknown, options: RequestOptions = {}): Promise<T> {
  const request = makeRequestSignal(options);
  try {
    const resp = await fetchWithAuth(buildUrl(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...requestHeaders(options, request.traceId)
      },
      signal: request.signal,
      body: JSON.stringify(payload)
    });
    return parseJsonResponse<T>(resp, path);
  } finally {
    request.cleanup();
  }
}

async function postFormData<T>(path: string, formData: FormData, options: RequestOptions = {}): Promise<T> {
  const request = makeRequestSignal({ timeoutMs: 60_000, ...options });
  try {
    const resp = await fetchWithAuth(buildUrl(path), {
      method: "POST",
      headers: requestHeaders(options, request.traceId),
      signal: request.signal,
      body: formData
    });
    return parseJsonResponse<T>(resp, path);
  } finally {
    request.cleanup();
  }
}

async function deleteJson(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  options: RequestOptions = {}
): Promise<void> {
  const request = makeRequestSignal(options);
  try {
    const resp = await fetchWithAuth(buildUrl(path, query), {
      method: "DELETE",
      headers: requestHeaders(options, request.traceId),
      signal: request.signal
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${path}`);
    }
  } finally {
    request.cleanup();
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
}, options?: RequestOptions): Promise<PagedArcades> {
  return fetchJson<PagedArcades>(buildUrl("/api/arcades", params), options);
}

export async function getArcadeDetail(sourceId: number, options?: RequestOptions): Promise<ArcadeDetail> {
  return fetchJson<ArcadeDetail>(buildUrl(`/api/arcades/${sourceId}`), options);
}

export async function listProvinces(options?: RequestOptions): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/provinces"), options);
}

export async function listCities(provinceCode: string, options?: RequestOptions): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/cities", { province_code: provinceCode }), options);
}

export async function listCounties(cityCode: string, options?: RequestOptions): Promise<RegionItem[]> {
  return fetchJson<RegionItem[]>(buildUrl("/api/regions/counties", { city_code: cityCode }), options);
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
  formData.append("idempotency_key", payload.idempotency_key || "");
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

export type ChatStreamMessage = { event: string; data: string };

export async function streamChatSession(
  sessionId: string,
  lastEventId: number | undefined,
  clientId: string | undefined,
  signal: AbortSignal,
  onMessage: (message: ChatStreamMessage) => void
): Promise<void> {
  const response = await fetchWithAuth(buildChatStreamUrl(sessionId, lastEventId, clientId), {
    headers: { Accept: "text/event-stream" },
    signal
  });
  if (!response.ok || !response.body) {
    throw new ApiRequestError({
      status: response.status,
      requestLabel: "chat stream",
      traceId: response.headers.get("x-request-trace-id"),
      detail: await response.text()
    });
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (block && !block.startsWith(":")) {
        let event = "message";
        const data: string[] = [];
        block.split("\n").forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        });
        if (data.length) onMessage({ event, data: data.join("\n") });
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
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

export async function getCurrentUser(): Promise<CurrentUser> {
  return fetchJson<CurrentUser>(buildUrl("/api/auth/me"));
}

export async function listKnowledgeSubmissions(): Promise<KnowledgeSubmission[]> {
  return fetchJson<KnowledgeSubmission[]>(buildUrl("/api/knowledge/submissions"));
}

export async function submitKnowledgeFile(
  file: File,
  title: string,
  description: string
): Promise<KnowledgeSubmission> {
  const formData = new FormData();
  formData.append("file", file);
  if (title.trim()) formData.append("title", title.trim());
  if (description.trim()) formData.append("description", description.trim());
  return postFormData<KnowledgeSubmission>("/api/knowledge/submissions", formData);
}

export async function withdrawKnowledgeSubmission(id: string): Promise<void> {
  return deleteJson(`/api/knowledge/submissions/${encodeURIComponent(id)}`);
}

export async function reviewKnowledgeSubmission(
  id: string,
  decision: "approved" | "rejected",
  note: string
): Promise<KnowledgeSubmission> {
  return postJson<KnowledgeSubmission>(`/api/knowledge/submissions/${encodeURIComponent(id)}/review`, {
    decision,
    note: note.trim() || null
  });
}

export async function lookupKnowledge(query: string, topK = 3, options?: RequestOptions): Promise<KnowledgeLookupResponse> {
  return fetchJson<KnowledgeLookupResponse>(buildUrl("/api/knowledge/lookup", { q: query, top_k: topK }), options);
}

export async function promoteKnowledgeArcadeCandidate(
  candidate: KnowledgeArcadeCandidate
): Promise<KnowledgeArcadePromotionResponse> {
  return postJson<KnowledgeArcadePromotionResponse>("/api/knowledge/arcade-candidates/promote", { candidate });
}

export async function reindexKnowledge(): Promise<KnowledgeStatus> {
  return postJson<KnowledgeStatus>("/api/knowledge/reindex", {});
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return postFormData<KnowledgeUploadResponse>("/api/knowledge/upload", formData);
}

export async function retryKnowledgeFile(relativePath: string): Promise<KnowledgeStatus> {
  return postJson<KnowledgeStatus>("/api/knowledge/files/retry", { relative_path: relativePath });
}

export async function deleteKnowledgeFile(relativePath: string): Promise<void> {
  return deleteJson("/api/knowledge/files", { relative_path: relativePath });
}

export async function deleteKnowledgeFilesBatch(relativePaths: string[]): Promise<KnowledgeStatus> {
  return postJson<KnowledgeStatus>("/api/knowledge/files/delete-batch", { relative_paths: relativePaths });
}
