import { formatTimeLabel } from "../lib/chatStream";
import { useAppStore } from "../stores/appStore";
import type { ChatSessionSummary } from "../types";

const NAV_ITEMS = [
  {
    key: "chat",
    index: "01",
    title: "Agent 对话",
    description: "问机厅、路线与出行决策"
  },
  {
    key: "arcades",
    index: "02",
    title: "机厅检索",
    description: "按地区、机种与地图筛选"
  },
  {
    key: "knowledge",
    index: "03",
    title: "知识库",
    description: "管理文档、索引与 RAG 来源"
  }
] as const;

type SidebarSessionItemProps = {
  item: ChatSessionSummary;
  active: boolean;
  deleting: boolean;
  onClick: () => void;
  onDelete: () => void;
};

function SidebarSessionItem({ item, active, deleting, onClick, onDelete }: SidebarSessionItemProps) {
  const statusLabel =
    item.status === "running"
      ? "进行中"
      : item.status === "failed"
        ? "异常"
        : item.status === "completed"
          ? "已完成"
          : "待处理";

  return (
    <li>
      <div className={`sidebar-session-wrap ${active ? "is-active" : ""}`}>
        <button type="button" onClick={onClick} className="sidebar-session">
          <span className="sidebar-session-status">{statusLabel}</span>
          <strong>{item.title}</strong>
          <p>{item.preview || "等待新的提问、检索或路线任务。"}</p>
          <small>{formatTimeLabel(item.updated_at)}</small>
        </button>
        <button type="button" className="sidebar-session-delete" onClick={onDelete} disabled={deleting}>
          {deleting ? "..." : "删除"}
        </button>
      </div>
    </li>
  );
}

type AppSidebarProps = {
  onStartNewSession: () => void;
  onOpenChatView: () => void;
  onOpenArcadesView: () => void;
  onOpenKnowledgeView: () => void;
  onRefresh: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
};

export function AppSidebar({
  onStartNewSession,
  onOpenChatView,
  onOpenArcadesView,
  onOpenKnowledgeView,
  onRefresh,
  onSelectSession,
  onDeleteSession
}: AppSidebarProps) {
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const viewMode = useAppStore((state) => state.viewMode);
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionId = useAppStore((state) => state.activeSessionId);
  const sessionsLoading = useAppStore((state) => state.sessionsLoading);
  const deletingSessionId = useAppStore((state) => state.deletingSessionId);
  const activeSessionStatus = useAppStore((state) => state.activeSessionStatus);
  const activeViewLabel = viewMode === "chat" ? "对话中枢" : viewMode === "arcades" ? "机厅检索" : "知识库维护";
  const activeStatusLabel =
    activeSessionStatus === "running"
      ? "会话进行中"
      : activeSessionStatus === "failed"
        ? "需要重试"
        : activeSessionStatus === "completed"
          ? "最近已完成"
          : "等待操作";

  return (
    <aside className={`app-sidebar ${sidebarOpen ? "is-open" : ""}`}>
      <div className="sidebar-top">
        <p className="sidebar-brand-kicker">Arcade Route Intelligence</p>
        <h1>Arcadegent</h1>
        <p className="sidebar-brand-copy">把机厅检索、路线建议和知识库线索汇成一个顺手的工作台。</p>
        <button type="button" className="sidebar-new" onClick={onStartNewSession}>
          新建会话
        </button>

        <div className="sidebar-hero-card">
          <div className="sidebar-hero-copy">
            <strong>{activeViewLabel}</strong>
            <small>{activeStatusLabel}</small>
          </div>
          <div className="sidebar-hero-stats">
            <div>
              <span>会话</span>
              <strong>{sessions.length}</strong>
            </div>
            <div>
              <span>当前</span>
              <strong>{activeSessionId ? "已接入" : "空闲"}</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="sidebar-section-label">工作区</div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const active = viewMode === item.key;
          const onClick =
            item.key === "chat"
              ? onOpenChatView
              : item.key === "arcades"
                ? onOpenArcadesView
                : onOpenKnowledgeView;
          return (
            <button
              key={item.key}
              type="button"
              className={`sidebar-nav-btn ${active ? "is-active" : ""}`}
              onClick={onClick}
            >
              <span className="sidebar-nav-index">{item.index}</span>
              <span className="sidebar-nav-copy">
                <strong>{item.title}</strong>
                <small>{item.description}</small>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-history-head">
        <div>
          <strong>历史会话</strong>
          <small>{sessions.length} 条记录</small>
        </div>
        <button type="button" onClick={onRefresh} disabled={sessionsLoading}>
          刷新
        </button>
      </div>

      <ul className="sidebar-history-list">
        {sessionsLoading ? <li className="sidebar-empty">会话加载中...</li> : null}
        {!sessionsLoading && sessions.length === 0 ? <li className="sidebar-empty">暂无历史会话</li> : null}
        {!sessionsLoading
          ? sessions.map((item) => (
              <SidebarSessionItem
                key={item.session_id}
                item={item}
                active={item.session_id === activeSessionId}
                deleting={deletingSessionId === item.session_id}
                onClick={() => onSelectSession(item.session_id)}
                onDelete={() => onDeleteSession(item.session_id)}
              />
            ))
          : null}
      </ul>
    </aside>
  );
}
