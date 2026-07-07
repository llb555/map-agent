import { create } from "zustand";
import type { ChatLifecycleEvent, ChatLifecycleState } from "../lib/chatLifecycle";
import { transitionChatLifecycle } from "../lib/chatLifecycle";
import type { StreamProgressItem } from "../lib/chatStream";
import { readInitialViewMode, syncViewModeInUrl } from "../lib/viewMode";
import type {
  ChatAttachment,
  ChatHistoryTurn,
  ChatMapArtifacts,
  ChatSessionStatus,
  ChatSessionSummary,
  ViewMode
} from "../types";

type Updater<T> = T | ((previous: T) => T);

function resolveUpdater<T>(next: Updater<T>, previous: T): T {
  return typeof next === "function" ? (next as (value: T) => T)(previous) : next;
}

type AppStore = {
  viewMode: ViewMode;
  sidebarOpen: boolean;
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  activeSessionStatus: ChatSessionStatus | null;
  chatLifecycle: ChatLifecycleState;
  turns: ChatHistoryTurn[];
  sessionsLoading: boolean;
  turnsLoading: boolean;
  deletingSessionId: string | null;
  inputValue: string;
  pendingChatFiles: File[];
  pendingChatAttachments: ChatAttachment[];
  chatError: string;
  activeSubagent: string | null;
  streamItems: StreamProgressItem[];
  activeMapArtifacts: ChatMapArtifacts | null;
  setViewMode: (viewMode: ViewMode, options?: { replace?: boolean; syncUrl?: boolean }) => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setSessions: (sessions: ChatSessionSummary[]) => void;
  setActiveSessionId: (sessionId: string | null) => void;
  setActiveSessionStatus: (status: ChatSessionStatus | null) => void;
  transitionChatLifecycle: (event: ChatLifecycleEvent) => void;
  setChatLifecycle: (state: ChatLifecycleState) => void;
  setTurns: (turns: Updater<ChatHistoryTurn[]>) => void;
  setSessionsLoading: (loading: boolean) => void;
  setTurnsLoading: (loading: boolean) => void;
  setDeletingSessionId: (sessionId: string | null) => void;
  setInputValue: (value: string) => void;
  setPendingChatFiles: (files: File[]) => void;
  setPendingChatAttachments: (attachments: ChatAttachment[]) => void;
  setChatError: (error: string) => void;
  setActiveSubagent: (subagent: string | null) => void;
  setStreamItems: (items: Updater<StreamProgressItem[]>) => void;
  setActiveMapArtifacts: (artifacts: Updater<ChatMapArtifacts | null>) => void;
  resetActiveSessionState: () => void;
};

export const useAppStore = create<AppStore>((set) => ({
  viewMode: readInitialViewMode(),
  sidebarOpen: false,
  sessions: [],
  activeSessionId: null,
  activeSessionStatus: null,
  chatLifecycle: "idle",
  turns: [],
  sessionsLoading: false,
  turnsLoading: false,
  deletingSessionId: null,
  inputValue: "",
  pendingChatFiles: [],
  pendingChatAttachments: [],
  chatError: "",
  activeSubagent: null,
  streamItems: [],
  activeMapArtifacts: null,
  setViewMode: (viewMode, options = {}) => {
    if (options.syncUrl !== false) {
      syncViewModeInUrl(viewMode, { replace: options.replace });
    }
    set({ viewMode });
  },
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSessions: (sessions) => set({ sessions }),
  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
  setActiveSessionStatus: (activeSessionStatus) => set({ activeSessionStatus }),
  transitionChatLifecycle: (event) => set((state) => {
    const chatLifecycle = transitionChatLifecycle(state.chatLifecycle, event);
    return state.chatLifecycle === chatLifecycle ? state : { chatLifecycle };
  }),
  setChatLifecycle: (chatLifecycle) => set({ chatLifecycle }),
  setTurns: (turns) => set((state) => ({ turns: resolveUpdater(turns, state.turns) })),
  setSessionsLoading: (sessionsLoading) => set({ sessionsLoading }),
  setTurnsLoading: (turnsLoading) => set({ turnsLoading }),
  setDeletingSessionId: (deletingSessionId) => set({ deletingSessionId }),
  setInputValue: (inputValue) => set({ inputValue }),
  setPendingChatFiles: (pendingChatFiles) => set({ pendingChatFiles }),
  setPendingChatAttachments: (pendingChatAttachments) => set({ pendingChatAttachments }),
  setChatError: (chatError) => set({ chatError }),
  setActiveSubagent: (activeSubagent) => set({ activeSubagent }),
  setStreamItems: (streamItems) => set((state) => ({
    streamItems: resolveUpdater(streamItems, state.streamItems)
  })),
  setActiveMapArtifacts: (activeMapArtifacts) => set((state) => ({
    activeMapArtifacts: resolveUpdater(activeMapArtifacts, state.activeMapArtifacts)
  })),
  resetActiveSessionState: () => set({
    activeSessionId: null,
    activeSessionStatus: null,
    chatLifecycle: "idle",
    turns: [],
    activeSubagent: null,
    activeMapArtifacts: null,
    pendingChatFiles: [],
    pendingChatAttachments: []
  })
}));
