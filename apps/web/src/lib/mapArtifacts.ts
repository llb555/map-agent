import type {
  AgentMapScene,
  ArcadeSummary,
  ChatMapArtifacts,
  ChatSessionDetail,
  ClientLocationContext,
  MapViewPayload,
  RouteSummary
} from "../types";

type LegacyMapArtifacts = {
  shops?: ArcadeSummary[] | null;
  route?: RouteSummary | null;
  client_location?: ClientLocationContext | null;
  destination?: ArcadeSummary | null;
  view_payload?: MapViewPayload | Record<string, unknown> | null;
  route_pending?: boolean;
};

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readScene(value: unknown): AgentMapScene | null {
  return value === "agent_route" || value === "agent_candidates" ? value : null;
}

function normalizeViewPayload(
  payload: MapViewPayload | Record<string, unknown> | null | undefined,
  fallbackScene: AgentMapScene
): MapViewPayload | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const schemaVersion = readNumber(payload.schema_version) ?? readNumber(payload.version) ?? 1;
  return {
    ...payload,
    schema_version: schemaVersion,
    scene: readScene(payload.scene) ?? fallbackScene
  };
}

function inferScene(input: LegacyMapArtifacts): AgentMapScene {
  const payloadScene = readScene(input.view_payload?.scene);
  if (payloadScene) {
    return payloadScene;
  }
  return input.route ? "agent_route" : "agent_candidates";
}

function adaptLegacyMapArtifacts(input: LegacyMapArtifacts): ChatMapArtifacts | null {
  const scene = inferScene(input);
  const shops = input.shops ?? [];
  const viewPayload = normalizeViewPayload(input.view_payload, scene);
  if (!input.route && !input.destination && !shops.length && !viewPayload) {
    return null;
  }
  return {
    schema_version: 1,
    scene,
    shops,
    route: input.route ?? null,
    client_location: input.client_location ?? null,
    destination: input.destination ?? null,
    view_payload: viewPayload,
    route_pending: Boolean(input.route_pending)
  };
}

function adaptVersionedMapScene(input: ChatMapArtifacts): ChatMapArtifacts | null {
  const schemaVersion = readNumber(input.schema_version) ?? 1;
  const scene = readScene(input.scene) ?? inferScene(input);
  const viewPayload = normalizeViewPayload(input.view_payload, scene);
  if (!input.route && !input.destination && !input.shops.length && !viewPayload) {
    return null;
  }
  return {
    ...input,
    schema_version: schemaVersion,
    scene,
    view_payload: viewPayload,
    route_pending: Boolean(input.route_pending)
  };
}

export function normalizeChatMapArtifacts(
  input: ChatMapArtifacts | LegacyMapArtifacts | null | undefined
): ChatMapArtifacts | null {
  if (!input) {
    return null;
  }
  if ("schema_version" in input || "scene" in input) {
    return adaptVersionedMapScene(input as ChatMapArtifacts);
  }
  return adaptLegacyMapArtifacts(input);
}

export function mapArtifactsFromSessionDetail(detail: ChatSessionDetail): ChatMapArtifacts | null {
  return normalizeChatMapArtifacts(
    detail.map_artifact ?? {
      shops: detail.shops,
      route: detail.route ?? null,
      client_location: detail.client_location ?? null,
      destination: detail.destination ?? null,
      view_payload: detail.view_payload ?? null,
      route_pending: false
    }
  );
}

export function hasRenderableMapArtifacts(input: ChatMapArtifacts | null | undefined): boolean {
  const artifacts = normalizeChatMapArtifacts(input);
  return Boolean(artifacts && (artifacts.route || artifacts.destination || artifacts.shops.length || artifacts.view_payload));
}
