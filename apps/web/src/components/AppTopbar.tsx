import { formatTimeLabel } from "../lib/chatStream";
import { useAppStore } from "../stores/appStore";
import { getAuthSession, signOut } from "../lib/auth";

export function AppTopbar() {
  const authSession = getAuthSession();
  const viewMode = useAppStore((state) => state.viewMode);
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionId = useAppStore((state) => state.activeSessionId);
  const activeSessionStatus = useAppStore((state) => state.activeSessionStatus);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const activeSessionUpdatedAt =
    sessions.find((session) => session.session_id === activeSessionId)?.updated_at ?? null;
  const title = viewMode === "chat" ? "Agent 对话" : viewMode === "arcades" ? "机厅检索" : "知识库管理";
  const subtitle =
    viewMode === "chat"
      ? "从自然语言问题进入，串联检索、地图与路线建议。"
      : viewMode === "arcades"
        ? "筛选门店、查看地图点位，并快速跳转导航。"
        : "管理 RAG 文档来源，保持知识库内容清晰可控。";
  const viewPill = viewMode === "chat" ? "Conversation Deck" : viewMode === "arcades" ? "Search Atlas" : "Knowledge Console";
  const statusLabel =
    activeSessionStatus === "running"
      ? "执行中"
      : activeSessionStatus === "failed"
        ? "需重试"
        : activeSessionStatus === "completed"
          ? "已完成"
          : "待命";

  return (
    <header className="topbar">
      <button type="button" className="menu-btn" onClick={toggleSidebar}>
        ☰
      </button>
      <div className="topbar-copy">
        <small className="topbar-kicker">Arcadegent Workspace</small>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="topbar-meta">
        {authSession ? (
          <div className="topbar-meta-block topbar-account">
            <span className="topbar-meta-label">账号</span>
            <strong>{authSession.user.email || "已认证用户"}</strong>
            <button type="button" onClick={() => void signOut()}>退出</button>
          </div>
        ) : null}
        <div className="topbar-meta-block">
          <span className="topbar-meta-label">模式</span>
          <strong>{viewPill}</strong>
        </div>
        <div className="topbar-meta-block">
          <span className="topbar-meta-label">状态</span>
          <strong>{statusLabel}</strong>
        </div>
        <div className="topbar-meta-block">
          <span className="topbar-meta-label">最近变更</span>
          <strong>{activeSessionUpdatedAt ? formatTimeLabel(activeSessionUpdatedAt) : "等待新的操作"}</strong>
        </div>
      </div>
    </header>
  );
}
