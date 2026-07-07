import { describe, expect, it } from "vitest";
import {
  canDispatchChat,
  isChatLifecycleTransitionAllowed,
  transitionChatLifecycle
} from "./chatLifecycle";

describe("chat lifecycle state machine", () => {
  it("allows the normal dispatch to streaming to completed flow", () => {
    const dispatching = transitionChatLifecycle("idle", "dispatch.start");
    const streaming = transitionChatLifecycle(dispatching, "stream.open");
    const completed = transitionChatLifecycle(streaming, "stream.complete");

    expect(dispatching).toBe("dispatching");
    expect(streaming).toBe("streaming");
    expect(completed).toBe("completed");
    expect(canDispatchChat(completed)).toBe(true);
  });

  it("keeps illegal late stream events from reviving completed sessions", () => {
    expect(transitionChatLifecycle("completed", "stream.open")).toBe("completed");
    expect(isChatLifecycleTransitionAllowed("completed", "stream.open")).toBe(false);
  });

  it("models reconnect and failure explicitly", () => {
    const reconnecting = transitionChatLifecycle("streaming", "stream.reconnect");
    const failed = transitionChatLifecycle(reconnecting, "stream.fail");

    expect(reconnecting).toBe("reconnecting");
    expect(failed).toBe("failed");
    expect(canDispatchChat(reconnecting)).toBe(false);
  });
});
