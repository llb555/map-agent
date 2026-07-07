export const CHAT_LIFECYCLE_STATES = [
  "idle",
  "dispatching",
  "streaming",
  "reconnecting",
  "completed",
  "failed"
] as const;

export type ChatLifecycleState = (typeof CHAT_LIFECYCLE_STATES)[number];

export type ChatLifecycleEvent =
  | "reset"
  | "dispatch.start"
  | "stream.open"
  | "stream.reconnect"
  | "stream.complete"
  | "stream.fail"
  | "history.running"
  | "history.completed"
  | "history.failed"
  | "history.idle";

const CHAT_LIFECYCLE_TRANSITIONS: Record<
  ChatLifecycleState,
  Partial<Record<ChatLifecycleEvent, ChatLifecycleState>>
> = {
  idle: {
    reset: "idle",
    "dispatch.start": "dispatching",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  },
  dispatching: {
    reset: "idle",
    "stream.open": "streaming",
    "stream.reconnect": "reconnecting",
    "stream.complete": "completed",
    "stream.fail": "failed",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  },
  streaming: {
    reset: "idle",
    "stream.open": "streaming",
    "stream.reconnect": "reconnecting",
    "stream.complete": "completed",
    "stream.fail": "failed",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  },
  reconnecting: {
    reset: "idle",
    "stream.open": "streaming",
    "stream.reconnect": "reconnecting",
    "stream.complete": "completed",
    "stream.fail": "failed",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  },
  completed: {
    reset: "idle",
    "dispatch.start": "dispatching",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  },
  failed: {
    reset: "idle",
    "dispatch.start": "dispatching",
    "history.running": "reconnecting",
    "history.completed": "completed",
    "history.failed": "failed",
    "history.idle": "idle"
  }
};

export function transitionChatLifecycle(
  current: ChatLifecycleState,
  event: ChatLifecycleEvent
): ChatLifecycleState {
  return CHAT_LIFECYCLE_TRANSITIONS[current][event] ?? current;
}

export function isChatLifecycleTransitionAllowed(
  current: ChatLifecycleState,
  event: ChatLifecycleEvent
): boolean {
  return CHAT_LIFECYCLE_TRANSITIONS[current][event] !== undefined;
}

export function isChatLifecycleBusy(state: ChatLifecycleState): boolean {
  return state === "dispatching" || state === "streaming" || state === "reconnecting";
}

export function canDispatchChat(state: ChatLifecycleState): boolean {
  return !isChatLifecycleBusy(state);
}

export function chatLifecycleFromSessionStatus(status: string | null | undefined): ChatLifecycleState {
  if (status === "running") {
    return "reconnecting";
  }
  if (status === "completed") {
    return "completed";
  }
  if (status === "failed") {
    return "failed";
  }
  return "idle";
}

export function chatLifecycleStatusText(state: ChatLifecycleState): string {
  if (state === "dispatching") {
    return "连接中...";
  }
  if (state === "streaming") {
    return "等待阶段事件...";
  }
  if (state === "reconnecting") {
    return "恢复连接中...";
  }
  if (state === "failed") {
    return "会话执行失败";
  }
  if (state === "completed") {
    return "阶段已结束";
  }
  return "等待会话继续...";
}
