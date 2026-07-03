import { useEffect } from "react";
import { AppSidebar } from "./components/AppSidebar";
import { AppTopbar } from "./components/AppTopbar";
import { ArcadeBrowser } from "./components/ArcadeBrowser";
import { ChatPanel } from "./components/ChatPanel";
import { KnowledgeManager } from "./components/KnowledgeManager";
import { useChatSessionController } from "./hooks/useChatSessionController";
import { readInitialViewMode } from "./lib/viewMode";
import { useAppStore } from "./stores/appStore";

export function App() {
  const viewMode = useAppStore((state) => state.viewMode);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);
  const chat = useChatSessionController();

  useEffect(() => {
    function handlePopState() {
      useAppStore.getState().setViewMode(readInitialViewMode(), { syncUrl: false });
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  return (
    <div className="app-shell">
      <AppSidebar
        onStartNewSession={chat.startNewSession}
        onOpenChatView={chat.openChatView}
        onOpenArcadesView={chat.openArcadesView}
        onOpenKnowledgeView={chat.openKnowledgeView}
        onRefresh={chat.refreshSessions}
        onSelectSession={chat.selectSession}
        onDeleteSession={(sessionId) => void chat.removeSession(sessionId)}
      />

      <button
        type="button"
        className={`sidebar-backdrop ${sidebarOpen ? "is-open" : ""}`}
        aria-label="关闭侧边栏"
        onClick={() => setSidebarOpen(false)}
      />

      <main className="app-main">
        <AppTopbar />

        {viewMode === "chat" ? (
          <ChatPanel
            onSubmit={chat.submitChat}
            onQuickAsk={chat.quickAsk}
            streamReplyTarget={chat.streamReplyTarget}
            streamReply={chat.streamReply}
            streamReplyActive={chat.streamReplyActive}
          />
        ) : viewMode === "arcades" ? (
          <ArcadeBrowser />
        ) : (
          <KnowledgeManager />
        )}
      </main>
    </div>
  );
}
