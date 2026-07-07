// Generated from backend/app/agent/events/event_types.py.
// Run `backend/.venv/bin/python backend/scripts/generate_stream_contract.py` after editing the backend event models.
// Do not edit by hand.

export const STREAM_EVENT_NAMES = [
  "session.started",
  "subagent.changed",
  "worker.started",
  "worker.completed",
  "worker.failed",
  "assistant.token",
  "tool.started",
  "tool.progress",
  "tool.completed",
  "tool.failed",
  "navigation.route_ready",
  "assistant.completed",
  "session.failed"
] as const;
export type ChatStreamEventName = (typeof STREAM_EVENT_NAMES)[number];

export type SessionStartedData = {
  intent: "search_nearby" | "navigate" | "search";
  active_subagent: string;
  model?: string | null;
  [key: string]: unknown;
};

export type SubagentChangedData = {
  active_subagent: string;
  to_subagent: string;
  reason?: string | null;
  from_subagent?: string | null;
  worker_run_id?: string | null;
  [key: string]: unknown;
};

export type WorkerStartedData = {
  worker: string;
  run_id: string;
  active_subagent: string;
  task_preview?: string | null;
  [key: string]: unknown;
};

export type WorkerCompletedData = {
  worker: string;
  run_id: string;
  active_subagent: string;
  status?: string | null;
  summary?: string | null;
  [key: string]: unknown;
};

export type WorkerFailedData = {
  worker: string;
  run_id: string;
  error: string;
  active_subagent: string;
  [key: string]: unknown;
};

export type AssistantTokenData = {
  delta: string;
  content: string;
  index: number;
  total: number;
  active_subagent: string;
  text_preview?: string | null;
  [key: string]: unknown;
};

export type ToolStartedData = {
  tool: string;
  call_id: string;
  active_subagent: string;
  worker_run_id?: string | null;
  [key: string]: unknown;
};

export type ToolProgressData = {
  tool: string;
  call_id: string;
  active_subagent: string;
  worker_run_id?: string | null;
  message?: string | null;
  progress?: number | null;
  [key: string]: unknown;
};

export type ToolCompletedData = {
  tool: string;
  call_id: string;
  active_subagent: string;
  worker_run_id?: string | null;
  distance_m?: number | null;
  [key: string]: unknown;
};

export type ToolFailedData = {
  tool: string;
  call_id: string;
  active_subagent: string;
  worker_run_id?: string | null;
  error: string;
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

export type NavigationRouteReadyData = {
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

export type AssistantCompletedData = {
  reply: string;
  active_subagent: string;
  [key: string]: unknown;
};

export type SessionFailedData = {
  error: string;
  active_subagent: string;
  [key: string]: unknown;
};

export type ChatStreamEventData = SessionStartedData | SubagentChangedData | WorkerStartedData | WorkerCompletedData | WorkerFailedData | AssistantTokenData | ToolStartedData | ToolProgressData | ToolCompletedData | ToolFailedData | NavigationRouteReadyData | AssistantCompletedData | SessionFailedData;

export type ChatStreamEnvelope = {
  id: number;
  session_id: string;
  event: ChatStreamEventName;
  at: string;
  data: ChatStreamEventData;
};

export function isChatStreamEventName(value: string): value is ChatStreamEventName {
  return (STREAM_EVENT_NAMES as readonly string[]).includes(value);
}
