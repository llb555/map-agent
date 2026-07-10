import { FormEvent, useCallback, useEffect, useRef } from "react";
import {
  deleteChatSession,
  dispatchChatSessionWithUploads,
  dispatchChatSession,
  getChatSession,
  listChatSessions,
  streamChatSession
} from "../api/client";
import { resolveClientLocationForSessionStart, warmupClientLocationCache } from "../lib/clientLocation";
import { canDispatchChat, chatLifecycleFromSessionStatus } from "../lib/chatLifecycle";
import {
  getChatClientId,
  readStoredStreamOffsets,
  readStoredActiveSessionId,
  writeStoredStreamOffset,
  writeStoredActiveSessionId
} from "../lib/chatSessionStorage";
import { parseChatStreamEnvelope, toProgressText, toVisibleTurns } from "../lib/chatStream";
import { mapArtifactsFromSessionDetail } from "../lib/mapArtifacts";
import { useAppStore } from "../stores/appStore";
import type {
  ChatMapArtifacts,
  ChatSessionDetail,
  ChatStreamEnvelope,
  RouteSummary
} from "../types";
import { useStreamReply } from "./useStreamReply";

function makeSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `s_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  return `s_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

function mapArtifactsFromSession(detail: ChatSessionDetail): ChatMapArtifacts | null {
  return mapArtifactsFromSessionDetail(detail);
}

function coerceStreamRoute(data: Record<string, unknown>): RouteSummary | null {
  const provider = data.provider;
  const mode = data.mode;
  if (provider !== "amap" && provider !== "google" && provider !== "none") {
    return null;
  }
  if (typeof mode !== "string" || !mode.trim()) {
    return null;
  }
  return {
    schema_version: typeof data.schema_version === "number" ? data.schema_version : 1,
    provider,
    mode,
    distance_m: typeof data.distance_m === "number" ? data.distance_m : null,
    duration_s: typeof data.duration_s === "number" ? data.duration_s : null,
    origin: typeof data.origin === "object" && data.origin !== null ? data.origin as RouteSummary["origin"] : null,
    destination:
      typeof data.destination === "object" && data.destination !== null
        ? data.destination as RouteSummary["destination"]
        : null,
    polyline: Array.isArray(data.polyline) ? data.polyline as RouteSummary["polyline"] : [],
    hint: typeof data.hint === "string" ? data.hint : null
  };
}

export function useChatSessionController() {
  const turns = useAppStore((state) => state.turns);
  const chatLifecycle = useAppStore((state) => state.chatLifecycle);

  const {
    applyStreamToken,
    cancelStreamReplyFlush,
    getStreamReplyTarget,
    resetStreamReply,
    streamReplyDisplay,
    streamReplyTarget,
    syncStreamReply,
    writeStreamReplyTarget
  } = useStreamReply();

  const streamRef = useRef<AbortController | null>(null);
  const clientIdRef = useRef("");
  const streamOffsetsRef = useRef<Record<string, number>>(readStoredStreamOffsets());
  if (!clientIdRef.current) {
    clientIdRef.current = getChatClientId();
  }

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.abort();
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    if ((chatLifecycle !== "streaming" && chatLifecycle !== "reconnecting") || streamReplyTarget.trim()) {
      return;
    }

    const last = turns[turns.length - 1];
    if (last?.role === "assistant" && last.content.trim() && last.content.length > getStreamReplyTarget().length) {
      writeStreamReplyTarget(last.content);
    }
  }, [chatLifecycle, getStreamReplyTarget, streamReplyTarget, turns, writeStreamReplyTarget]);

  useEffect(() => {
    void loadSessionList(readStoredActiveSessionId() || undefined);
    void warmupClientLocationCache();
  }, []);

  useEffect(() => {
    return () => {
      cancelStreamReplyFlush();
      stopStream();
    };
  }, [cancelStreamReplyFlush, stopStream]);

  function pushStreamEnvelope(envelope: ChatStreamEnvelope): void {
    useAppStore.getState().setStreamItems([
      {
        id: envelope.id,
        event: envelope.event,
        text: toProgressText(envelope),
        at: envelope.at
      }
    ]);
  }

  function commitStreamReply(reply: string): void {
    const normalized = reply.trim();
    if (!normalized) {
      return;
    }

    useAppStore.getState().setTurns((previous) => {
      const next = [...previous];
      const last = next[next.length - 1];

      if (last?.role === "assistant") {
        if (last.content === normalized) {
          return previous;
        }
        if (normalized.startsWith(last.content) || last.content.startsWith(normalized)) {
          next[next.length - 1] = {
            ...last,
            content: normalized
          };
          return next;
        }
      }

      next.push({
        role: "assistant",
        content: normalized,
        created_at: new Date().toISOString()
      });
      return next;
    });
  }

  function updateStreamOffset(sessionId: string, offset: number): void {
    streamOffsetsRef.current[sessionId] = Math.max(streamOffsetsRef.current[sessionId] ?? 0, offset);
    writeStoredStreamOffset(sessionId, streamOffsetsRef.current[sessionId]);
  }

  function makeIdempotencyKey(sessionId: string): string {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `run_${sessionId}_${crypto.randomUUID().replace(/-/g, "")}`;
    }
    return `run_${sessionId}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  }

  function startStream(sessionId: string, lastEventId?: number): void {
    stopStream();
    const store = useAppStore.getState();
    store.setStreamItems([]);
    store.setActiveSubagent(null);
    store.setActiveSessionStatus("running");
    store.transitionChatLifecycle("stream.reconnect");
    resetStreamReply();

    const resumeOffset = typeof lastEventId === "number" ? lastEventId : streamOffsetsRef.current[sessionId];
    const source = new AbortController();
    streamRef.current = source;

    const handleEvent = (message: { data: string }) => {
      if (streamRef.current !== source) {
        return;
      }

      if (!message.data) {
        return;
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(message.data);
      } catch {
        return;
      }

      if (!parsed || typeof parsed !== "object") {
        return;
      }

      const envelope = parseChatStreamEnvelope(parsed);
      if (!envelope) {
        return;
      }

      const currentStore = useAppStore.getState();
      updateStreamOffset(sessionId, envelope.id);

      if (envelope.event === "session.started") {
        currentStore.setActiveSessionStatus("running");
        const current = envelope.data.active_subagent;
        if (typeof current === "string" && current) {
          currentStore.setActiveSubagent(current);
        }
      }

      if (envelope.event === "subagent.changed") {
        const next = envelope.data.to_subagent ?? envelope.data.active_subagent;
        if (typeof next === "string" && next) {
          currentStore.setActiveSubagent(next);
        }
      }

      if (envelope.event === "assistant.token") {
        applyStreamToken(envelope.data);
      }

      if (envelope.event === "navigation.route_ready") {
        const route = coerceStreamRoute(envelope.data);
        if (route) {
          currentStore.setActiveMapArtifacts((previous) => ({
            schema_version: previous?.schema_version ?? 1,
            scene: "agent_route",
            shops: previous?.shops ?? [],
            route,
            client_location: previous?.client_location ?? null,
            destination: previous?.destination ?? null,
            view_payload: previous?.view_payload ?? { schema_version: 1, scene: "agent_route" },
            route_pending: true
          }));
        }
      }

      if (envelope.event === "assistant.completed") {
        currentStore.setActiveSessionStatus("completed");
        currentStore.transitionChatLifecycle("stream.complete");
        const reply = envelope.data.reply;
        if (typeof reply === "string" && reply) {
          if (reply.length >= getStreamReplyTarget().length) {
            syncStreamReply(reply);
          }
          commitStreamReply(reply);
        }
      }

      if (envelope.event === "session.failed") {
        currentStore.setActiveSessionStatus("failed");
        currentStore.transitionChatLifecycle("stream.fail");
        const error = envelope.data.error;
        currentStore.setChatError(typeof error === "string" && error.trim() ? error : "会话执行失败");
      }

      pushStreamEnvelope(envelope);

      if (envelope.event === "assistant.completed" || envelope.event === "session.failed") {
        stopStream();
        void loadSession(sessionId, {
          preserveStreamState: true,
          reconnectStream: false
        });
        void loadSessionList(sessionId, { preserveStreamState: true });
      }
    };

    if (streamRef.current === source) {
      const currentStore = useAppStore.getState();
      currentStore.setActiveSessionStatus("running");
      currentStore.transitionChatLifecycle("stream.open");
    }

    void streamChatSession(
      sessionId,
      resumeOffset,
      clientIdRef.current,
      source.signal,
      handleEvent
    ).then(() => {
      if (streamRef.current !== source) return;
      stopStream();
      void loadSession(sessionId, { preserveStreamState: true, reconnectStream: false });
    }).catch((error) => {
      if (streamRef.current !== source) {
        return;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      const store = useAppStore.getState();
      if (store.chatLifecycle === "streaming") {
        store.transitionChatLifecycle("stream.reconnect");
      }
      stopStream();
      void loadSession(sessionId, {
        preserveStreamState: true,
        reconnectStream: false
      });
    });
  }

  function applySessionDetail(
    sessionId: string,
    detail: ChatSessionDetail,
    options?: { preserveStreamState?: boolean; reconnectStream?: boolean }
  ): void {
    const preserveStreamState = options?.preserveStreamState ?? false;
    const reconnectStream = options?.reconnectStream ?? true;
    const store = useAppStore.getState();

    store.setActiveSessionId(sessionId);
    writeStoredActiveSessionId(sessionId);
    store.setTurns(toVisibleTurns(detail.turns));
    store.setActiveSubagent(detail.active_subagent || null);
    store.setActiveSessionStatus(detail.status);
    store.setChatLifecycle(chatLifecycleFromSessionStatus(detail.status));
    store.setActiveMapArtifacts(mapArtifactsFromSession(detail));

    if (!preserveStreamState) {
      store.setStreamItems([]);
      resetStreamReply();
    }

    if (detail.reply && detail.reply.trim() && detail.reply.length > getStreamReplyTarget().length) {
    if (detail.status === "running") {
        writeStreamReplyTarget(detail.reply);
      } else {
        syncStreamReply(detail.reply);
      }
    }

    if (detail.status === "failed") {
      store.setChatError(detail.last_error?.trim() ? detail.last_error : "会话执行失败");
    } else {
      store.setChatError("");
    }

    if (detail.status === "running") {
      if (reconnectStream) {
        startStream(sessionId);
      }
      return;
    }

    if (!preserveStreamState) {
      stopStream();
    }
  }

  async function loadSessionList(
    preferredSessionId?: string,
    options?: { preserveStreamState?: boolean }
  ): Promise<void> {
    const preserveStreamState = options?.preserveStreamState ?? false;
    const store = useAppStore.getState();
    store.setSessionsLoading(true);

    try {
      const rows = await listChatSessions(60, clientIdRef.current);
      const latestStore = useAppStore.getState();
      latestStore.setSessions(rows);

      if (!rows.length) {
        writeStoredActiveSessionId(null);
        latestStore.setActiveSessionId(null);
        latestStore.setActiveSessionStatus(null);
        latestStore.setTurns([]);
        latestStore.setActiveSubagent(null);
        latestStore.setActiveMapArtifacts(null);
        if (!preserveStreamState) {
          stopStream();
          latestStore.setStreamItems([]);
          resetStreamReply();
          latestStore.transitionChatLifecycle("history.idle");
        }
        return;
      }

      const currentActiveSessionId = latestStore.activeSessionId;
      const currentActiveStatus = latestStore.activeSessionStatus;
      const hasPreferred = preferredSessionId ? rows.some((item) => item.session_id === preferredSessionId) : false;
      const hasActive = currentActiveSessionId
        ? rows.some((item) => item.session_id === currentActiveSessionId)
        : false;
      const targetId = hasPreferred
        ? preferredSessionId
        : hasActive
          ? currentActiveSessionId
          : currentActiveSessionId && currentActiveStatus === "running"
            ? null
            : rows[0].session_id;

      if (targetId && targetId !== currentActiveSessionId) {
        await loadSession(targetId, { preserveStreamState, reconnectStream: true });
      }
    } catch (err) {
      useAppStore.getState().setChatError(err instanceof Error ? err.message : "加载会话列表失败");
    } finally {
      useAppStore.getState().setSessionsLoading(false);
    }
  }

  async function loadSession(
    sessionId: string,
    options?: { preserveStreamState?: boolean; reconnectStream?: boolean }
  ): Promise<ChatSessionDetail | null> {
    const preserveStreamState = options?.preserveStreamState ?? false;
    const reconnectStream = options?.reconnectStream ?? true;
    const store = useAppStore.getState();
    store.setTurnsLoading(true);
    store.setChatError("");

    try {
      const detail = await getChatSession(sessionId, clientIdRef.current);
      applySessionDetail(sessionId, detail, { preserveStreamState, reconnectStream });
      return detail;
    } catch (err) {
      useAppStore.getState().setChatError(err instanceof Error ? err.message : "加载会话失败");
      return null;
    } finally {
      useAppStore.getState().setTurnsLoading(false);
    }
  }

  function openChatView(): void {
    const store = useAppStore.getState();
    store.setViewMode("chat");
    store.setSidebarOpen(false);
  }

  function openArcadesView(): void {
    const store = useAppStore.getState();
    store.setViewMode("arcades");
    store.setSidebarOpen(false);
  }

  function openKnowledgeView(): void {
    const store = useAppStore.getState();
    store.setViewMode("knowledge");
    store.setSidebarOpen(false);
  }

  function startNewSession(): void {
    stopStream();
    const store = useAppStore.getState();
    store.setViewMode("chat");
    store.resetActiveSessionState();
    writeStoredActiveSessionId(null);
    store.setInputValue("");
    store.setPendingChatFiles([]);
    store.setPendingChatAttachments([]);
    store.setChatError("");
    store.setSidebarOpen(false);
    store.setStreamItems([]);
    resetStreamReply();
  }

  async function submitChat(event: FormEvent): Promise<void> {
    event.preventDefault();
    const currentState = useAppStore.getState();
    const message = currentState.inputValue.trim();
    const pendingFiles = currentState.pendingChatFiles;
    const pendingAttachments = currentState.pendingChatAttachments;
    if ((!message && pendingFiles.length === 0) || !canDispatchChat(currentState.chatLifecycle)) {
      return;
    }

    const isNewSession = !currentState.activeSessionId;
    const previousSessionId = currentState.activeSessionId;
    const previousSessionStatus = currentState.activeSessionStatus;
    const sessionId = currentState.activeSessionId || makeSessionId();
    const idempotencyKey = makeIdempotencyKey(sessionId);
    const optimisticCreatedAt = new Date().toISOString();

    currentState.transitionChatLifecycle("dispatch.start");
    currentState.setChatError("");

    try {
      const location = isNewSession ? await resolveClientLocationForSessionStart() : undefined;
      const store = useAppStore.getState();

      store.setInputValue("");
      store.setPendingChatFiles([]);
      store.setPendingChatAttachments([]);
      store.setActiveSessionId(sessionId);
      writeStoredActiveSessionId(sessionId);
      store.setActiveSessionStatus("running");
      store.setActiveMapArtifacts(null);
      store.setTurns((previous) => [
        ...previous,
        {
          role: "user",
          content: message || "已上传附件",
          payload: pendingAttachments.length ? { attachments: pendingAttachments } : undefined,
          created_at: optimisticCreatedAt
        }
      ]);

      const payload = {
        session_id: sessionId,
        client_id: clientIdRef.current,
        idempotency_key: idempotencyKey,
        message,
        location: location ?? undefined,
        page_size: 5,
        attachments: pendingAttachments
      };
      const dispatched = pendingFiles.length
        ? await dispatchChatSessionWithUploads(payload, pendingFiles)
        : await dispatchChatSession(payload);
      const latestStore = useAppStore.getState();
      latestStore.setActiveSessionId(dispatched.session_id);
      writeStoredActiveSessionId(dispatched.session_id);
      latestStore.setActiveSessionStatus(dispatched.status);
      latestStore.transitionChatLifecycle("stream.reconnect");
      startStream(dispatched.session_id);
      await loadSessionList(dispatched.session_id, { preserveStreamState: true });
    } catch (err) {
      const store = useAppStore.getState();
      store.setChatError(err instanceof Error ? err.message : "发送失败");
      store.setInputValue(message);
      store.setPendingChatFiles(pendingFiles);
      store.setPendingChatAttachments(pendingAttachments);
      store.setActiveSessionId(previousSessionId);
      writeStoredActiveSessionId(previousSessionId);
      store.setActiveSessionStatus(previousSessionStatus);
      store.setChatLifecycle(chatLifecycleFromSessionStatus(previousSessionStatus));
      store.setTurns((previous) => {
        const next = [...previous];
        const last = next[next.length - 1];
        if (last && last.role === "user" && last.content === message && last.created_at === optimisticCreatedAt) {
          next.pop();
        }
        return next;
      });
      store.setStreamItems([]);
      store.setActiveSubagent(null);
      store.setActiveMapArtifacts(null);
      resetStreamReply();
      stopStream();
    }
  }

  function quickAsk(prompt: string): void {
    const store = useAppStore.getState();
    store.setInputValue(prompt);
    store.setViewMode("chat");
    store.setSidebarOpen(false);
  }

  async function removeSession(sessionId: string): Promise<void> {
    const currentState = useAppStore.getState();
    if (currentState.deletingSessionId || !canDispatchChat(currentState.chatLifecycle)) {
      return;
    }

    const ok = window.confirm("确认删除这个历史会话吗？");
    if (!ok) {
      return;
    }

    currentState.setDeletingSessionId(sessionId);
    currentState.setChatError("");

    try {
      await deleteChatSession(sessionId, clientIdRef.current);
      const store = useAppStore.getState();
      const isActive = store.activeSessionId === sessionId;

      if (isActive) {
        store.resetActiveSessionState();
        writeStoredActiveSessionId(null);
        store.setStreamItems([]);
        resetStreamReply();
      }

      await loadSessionList(isActive ? undefined : store.activeSessionId || undefined);
    } catch (err) {
      useAppStore.getState().setChatError(err instanceof Error ? err.message : "删除会话失败");
    } finally {
      useAppStore.getState().setDeletingSessionId(null);
    }
  }

  function selectSession(sessionId: string): void {
    stopStream();
    const store = useAppStore.getState();
    store.setViewMode("chat");
    void loadSession(sessionId);
    store.setSidebarOpen(false);
  }

  function refreshSessions(): void {
    void loadSessionList(useAppStore.getState().activeSessionId || undefined);
  }

  return {
    openChatView,
    openArcadesView,
    openKnowledgeView,
    startNewSession,
    submitChat,
    quickAsk,
    removeSession,
    selectSession,
    refreshSessions,
    streamReplyTarget,
    streamReply: streamReplyDisplay,
    streamReplyActive:
      chatLifecycle === "dispatching" ||
      chatLifecycle === "streaming" ||
      chatLifecycle === "reconnecting" ||
      streamReplyDisplay.length < streamReplyTarget.length
  };
}
