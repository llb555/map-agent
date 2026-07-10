export type AuthUser = {
  id: string;
  email: string | null;
};

export type AuthSession = {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  user: AuthUser;
};

const SESSION_KEY = "arcadegent.auth.session.v1";
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.trim().replace(/\/$/, "") || "";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim() || "";
let currentSession: AuthSession | null = readSession();
let refreshPromise: Promise<AuthSession | null> | null = null;
const listeners = new Set<(session: AuthSession | null) => void>();

export function isAuthConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

function readSession(): AuthSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.access_token || !parsed.refresh_token || !parsed.user?.id) return null;
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

function writeSession(session: AuthSession | null): void {
  currentSession = session;
  try {
    if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // The in-memory session still supports the active tab.
  }
  listeners.forEach((listener) => listener(session));
}

function normalizeSession(payload: Record<string, unknown>): AuthSession {
  const expiresIn = typeof payload.expires_in === "number" ? payload.expires_in : 3600;
  const user = payload.user as Record<string, unknown> | undefined;
  if (typeof payload.access_token !== "string" || typeof payload.refresh_token !== "string" || typeof user?.id !== "string") {
    throw new Error("认证服务返回了无效会话");
  }
  return {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    user: { id: user.id, email: typeof user.email === "string" ? user.email : null }
  };
}

async function authRequest(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!isAuthConfigured()) throw new Error("请配置 VITE_SUPABASE_URL 和 VITE_SUPABASE_ANON_KEY");
  const response = await fetch(`${SUPABASE_URL}/auth/v1/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: SUPABASE_ANON_KEY },
    body: JSON.stringify(body)
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    const message = payload.msg ?? payload.message ?? payload.error_description ?? "认证请求失败";
    throw new Error(String(message));
  }
  return payload;
}

export async function signIn(email: string, password: string): Promise<AuthSession> {
  const session = normalizeSession(await authRequest("token?grant_type=password", { email, password }));
  writeSession(session);
  return session;
}

export async function signUp(email: string, password: string): Promise<AuthSession | null> {
  const payload = await authRequest("signup", { email, password });
  if (!payload.access_token) return null;
  const session = normalizeSession(payload);
  writeSession(session);
  return session;
}

export async function refreshSession(): Promise<AuthSession | null> {
  if (!currentSession?.refresh_token) return null;
  if (refreshPromise) return refreshPromise;
  refreshPromise = authRequest("token?grant_type=refresh_token", { refresh_token: currentSession.refresh_token })
    .then((payload) => {
      const session = normalizeSession(payload);
      writeSession(session);
      return session;
    })
    .catch(() => {
      writeSession(null);
      return null;
    })
    .finally(() => { refreshPromise = null; });
  return refreshPromise;
}

export async function getValidAccessToken(): Promise<string | null> {
  if (!currentSession) return null;
  if (currentSession.expires_at > Math.floor(Date.now() / 1000) + 60) return currentSession.access_token;
  return (await refreshSession())?.access_token ?? null;
}

export function getAuthSession(): AuthSession | null {
  return currentSession;
}

export function subscribeAuth(listener: (session: AuthSession | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function signOut(): Promise<void> {
  const token = currentSession?.access_token;
  writeSession(null);
  if (token && isAuthConfigured()) {
    await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
      method: "POST",
      headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${token}` }
    }).catch(() => undefined);
  }
}

export async function fetchWithAuth(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const request = async (token: string | null) => fetch(input, {
    ...init,
    headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
  });
  let response = await request(await getValidAccessToken());
  if (response.status === 401 && currentSession) {
    response = await request((await refreshSession())?.access_token ?? null);
  }
  return response;
}
