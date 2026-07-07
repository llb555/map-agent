const CLIENT_ID_KEY = "arcadegent.chat.clientId.v1";
const ACTIVE_SESSION_ID_KEY = "arcadegent.chat.activeSessionId.v1";
const STREAM_OFFSETS_KEY = "arcadegent.chat.streamOffsets.v1";

let fallbackClientId: string | null = null;
let fallbackActiveSessionId: string | null = null;
let fallbackStreamOffsets: Record<string, number> = {};

function makeLocalId(prefix: string): string {
  const cryptoApi = typeof globalThis.crypto !== "undefined" ? globalThis.crypto : null;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return `${prefix}_${cryptoApi.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  }
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function readLocalStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function normalizeStoredId(value: string | null): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

export function getChatClientId(): string {
  const storage = readLocalStorage();
  if (!storage) {
    if (!fallbackClientId) {
      fallbackClientId = makeLocalId("c");
    }
    return fallbackClientId;
  }

  const existing = normalizeStoredId(storage.getItem(CLIENT_ID_KEY));
  if (existing) {
    return existing;
  }

  const created = makeLocalId("c");
  try {
    storage.setItem(CLIENT_ID_KEY, created);
  } catch {
    fallbackClientId = created;
  }
  return created;
}

export function readStoredActiveSessionId(): string | null {
  const storage = readLocalStorage();
  if (!storage) {
    return fallbackActiveSessionId;
  }
  return normalizeStoredId(storage.getItem(ACTIVE_SESSION_ID_KEY));
}

export function writeStoredActiveSessionId(sessionId: string | null): void {
  fallbackActiveSessionId = normalizeStoredId(sessionId);
  const storage = readLocalStorage();
  if (!storage) {
    return;
  }
  try {
    if (fallbackActiveSessionId) {
      storage.setItem(ACTIVE_SESSION_ID_KEY, fallbackActiveSessionId);
    } else {
      storage.removeItem(ACTIVE_SESSION_ID_KEY);
    }
  } catch {
    // Keep the in-memory fallback so the active tab still behaves consistently.
  }
}

export function readStoredStreamOffsets(): Record<string, number> {
  const storage = readLocalStorage();
  if (!storage) {
    return { ...fallbackStreamOffsets };
  }
  try {
    const raw = JSON.parse(storage.getItem(STREAM_OFFSETS_KEY) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return {};
    }
    const offsets: Record<string, number> = {};
    Object.entries(raw).forEach(([sessionId, offset]) => {
      if (typeof offset === "number" && Number.isFinite(offset) && offset > 0) {
        offsets[sessionId] = offset;
      }
    });
    return offsets;
  } catch {
    return {};
  }
}

export function writeStoredStreamOffset(sessionId: string, offset: number): void {
  if (!sessionId || !Number.isFinite(offset) || offset <= 0) {
    return;
  }
  fallbackStreamOffsets = {
    ...fallbackStreamOffsets,
    [sessionId]: Math.max(fallbackStreamOffsets[sessionId] ?? 0, offset)
  };
  const storage = readLocalStorage();
  if (!storage) {
    return;
  }
  try {
    const offsets = readStoredStreamOffsets();
    offsets[sessionId] = Math.max(offsets[sessionId] ?? 0, offset);
    storage.setItem(STREAM_OFFSETS_KEY, JSON.stringify(offsets));
  } catch {
    // The in-memory fallback keeps reconnect working for the active tab.
  }
}
