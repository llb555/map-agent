import { ChangeEvent, Fragment, FormEvent, useEffect, useMemo, useRef } from "react";
import { formatSubagentLabel, formatTimeLabel } from "../lib/chatStream";
import { useAppStore } from "../stores/appStore";
import type { ChatAttachment } from "../types";
import { MarkdownMessage } from "./MarkdownMessage";
import { AgentMapCard } from "./map/AgentMapCard";

const QUICK_PROMPTS = [
  "帮我找找适合下班后去的机厅",
  "南京最多机台的机厅是哪家？",
  "给我一条从当前位置到最近机厅的路线建议"
];

type ChatPanelProps = {
  onSubmit: (event: FormEvent) => Promise<void>;
  onQuickAsk: (prompt: string) => void;
  streamReplyTarget: string;
  streamReply: string;
  streamReplyActive: boolean;
};

export function ChatPanel({
  onSubmit,
  onQuickAsk,
  streamReplyTarget,
  streamReply,
  streamReplyActive
}: ChatPanelProps) {
  const turns = useAppStore((state) => state.turns);
  const loading = useAppStore((state) => state.turnsLoading);
  const sending = useAppStore((state) => state.sending);
  const inputValue = useAppStore((state) => state.inputValue);
  const setInputValue = useAppStore((state) => state.setInputValue);
  const pendingChatFiles = useAppStore((state) => state.pendingChatFiles);
  const pendingChatAttachments = useAppStore((state) => state.pendingChatAttachments);
  const setPendingChatAttachments = useAppStore((state) => state.setPendingChatAttachments);
  const setPendingChatFiles = useAppStore((state) => state.setPendingChatFiles);
  const error = useAppStore((state) => state.chatError);
  const streamConnected = useAppStore((state) => state.streamConnected);
  const activeSubagent = useAppStore((state) => state.activeSubagent);
  const streamItems = useAppStore((state) => state.streamItems);
  const awaitingAssistant = useAppStore((state) => state.awaitingAssistant);
  const mapArtifacts = useAppStore((state) => state.activeMapArtifacts);
  const endRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const turnsForRender = useMemo(() => {
    if (!turns.length) {
      return turns;
    }

    const last = turns[turns.length - 1];
    if (last.role !== "assistant") {
      return turns;
    }

    const hasStreamingContext =
      awaitingAssistant || sending || streamConnected || streamReplyActive || streamReplyTarget.trim().length > 0;
    if (!hasStreamingContext) {
      return turns;
    }

    if (awaitingAssistant) {
      return turns.slice(0, -1);
    }

    const streamText = streamReplyTarget.trim();
    if (!streamText) {
      return turns.slice(0, -1);
    }

    const lastText = last.content.trim();
    const overlaps =
      lastText === streamText || lastText.startsWith(streamText) || streamText.startsWith(lastText);

    if (overlaps) {
      return turns.slice(0, -1);
    }

    return turns;
  }, [awaitingAssistant, sending, streamConnected, streamReplyActive, streamReplyTarget, turns]);

  const lastAssistantReply = useMemo(() => {
    for (let idx = turnsForRender.length - 1; idx >= 0; idx -= 1) {
      const turn = turnsForRender[idx];
      if (turn.role === "assistant") {
        return turn.content;
      }
    }
    return "";
  }, [turnsForRender]);

  const showStreamReply =
    streamReply.trim().length > 0 &&
    (streamReplyActive || !lastAssistantReply || !lastAssistantReply.startsWith(streamReply));
  const showStreamStage = streamItems.length > 0 || sending || streamConnected || streamReplyActive || awaitingAssistant;
  const showStreamingBubble = showStreamReply || awaitingAssistant;
  const showMapCard = Boolean(
    mapArtifacts && (mapArtifacts.route || mapArtifacts.shops.length > 0 || mapArtifacts.view_payload)
  );
  const showEmptyState = turns.length === 0 && !showStreamingBubble && !showStreamStage && !showMapCard;
  const latestStreamItem = streamItems.length ? streamItems[streamItems.length - 1] : null;
  const composerBusy = sending || awaitingAssistant;
  const hasPendingAttachments = pendingChatAttachments.length > 0;
  const stageStatusText =
    latestStreamItem?.text
    ?? (streamConnected
      ? "等待阶段事件..."
      : sending
        ? "连接中..."
        : awaitingAssistant
          ? "等待会话继续..."
          : "阶段已结束");
  const stageStatusMeta = latestStreamItem ? formatTimeLabel(latestStreamItem.at) : "实时同步中...";

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnsForRender, loading, sending, streamItems, streamReply, awaitingAssistant, showStreamStage, showMapCard]);

  useEffect(() => {
    return () => {
      pendingChatAttachments.forEach((attachment) => {
        if (attachment.image_data_url?.startsWith("blob:")) {
          URL.revokeObjectURL(attachment.image_data_url);
        }
      });
    };
  }, [pendingChatAttachments]);

  const lastAssistantIndex = useMemo(() => {
    for (let idx = turnsForRender.length - 1; idx >= 0; idx -= 1) {
      if (turnsForRender[idx].role === "assistant") {
        return idx;
      }
    }
    return -1;
  }, [turnsForRender]);

  const renderMapCard = (key: string, animationIndex: number) => {
    if (!showMapCard || !mapArtifacts) {
      return null;
    }
    return (
      <li
        key={key}
        className="chat-message assistant"
        style={{ animationDelay: `${Math.min(animationIndex, 8) * 45}ms` }}
      >
        <div className="chat-message-stack chat-map-stack">
          <div className="chat-message-meta">
            <span className="chat-message-role">地图联动</span>
            <small>候选与路线同步展示</small>
          </div>
          <div className="chat-map-card-item">
            <AgentMapCard artifacts={mapArtifacts} />
          </div>
        </div>
      </li>
    );
  };

  function normalizeAttachment(file: File): ChatAttachment {
    const isImage = file.type.startsWith("image/");
    return {
      name: file.name,
      mime_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      kind: isImage ? "image" : "document",
      preview_text: isImage ? "图片待发送" : "文件待发送",
      image_data_url: isImage ? URL.createObjectURL(file) : null
    };
  }

  function handleFilePick(event: ChangeEvent<HTMLInputElement>): void {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }
    const attachments = files.map((file) => normalizeAttachment(file));
    setPendingChatFiles(files);
    setPendingChatAttachments(attachments);
  }

  function removePendingAttachment(index: number): void {
    const nextAttachments = [...pendingChatAttachments];
    nextAttachments.splice(index, 1);
    setPendingChatAttachments(nextAttachments);
    setPendingChatFiles(pendingChatFiles.filter((_, fileIndex) => fileIndex !== index));
  }

  function renderAttachmentChips(attachments: ChatAttachment[], options?: { removable?: boolean }) {
    if (!attachments.length) {
      return null;
    }
    const removable = options?.removable ?? false;
    return (
      <div className="chat-attachment-list">
        {attachments.map((attachment, index) => (
          <div key={`${attachment.name}-${index}`} className="chat-attachment-chip">
            {attachment.image_data_url ? (
              <img src={attachment.image_data_url} alt={attachment.name} className="chat-attachment-thumb" />
            ) : null}
            <div className="chat-attachment-copy">
              <strong>{attachment.name}</strong>
              <span>{attachment.kind === "image" ? "图片附件" : "文件附件"}</span>
            </div>
            {removable && !composerBusy ? (
              <button type="button" className="chat-attachment-remove" onClick={() => removePendingAttachment(index)}>
                移除
              </button>
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="chat-view">
      <div className="chat-scroll">
        {showEmptyState ? (
          <div className="chat-empty">
            <div className="chat-empty-kicker">Arcade Search · Route · Knowledge</div>
            <p className="chat-empty-title">把“去哪打”“怎么去”“值不值得去”放到一个首页里解决。</p>
            <p className="chat-empty-subtitle">
              直接描述你的需求，Arcadegent 会把机厅检索、知识库线索和地图路线一起串起来。
            </p>
            <div className="chat-empty-stat-row">
              <div className="chat-empty-stat">
                <strong>Agent 对话</strong>
                <span>自然语言提问，实时返回回复与执行阶段。</span>
              </div>
              <div className="chat-empty-stat">
                <strong>地图联动</strong>
                <span>候选门店、临时点位与路线卡片同步展示。</span>
              </div>
              <div className="chat-empty-stat">
                <strong>知识回查</strong>
                <span>数据库没命中时，继续补上知识库与高德候选。</span>
              </div>
            </div>
            <div className="chat-quick-grid">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="quick-chip"
                  onClick={() => onQuickAsk(prompt)}
                  disabled={composerBusy}
                >
                  <span className="quick-chip-kicker">快速开始</span>
                  <strong>{prompt}</strong>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="chat-message-list">
            {turnsForRender.map((turn, index) => (
              <Fragment key={`${turn.created_at}-${index}`}>
                <li
                  className={`chat-message ${turn.role}`}
                  style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
                >
                  <div className="chat-message-stack">
                    <div className="chat-message-meta">
                      <span className="chat-message-role">{turn.role === "assistant" ? "Arcadegent" : "你"}</span>
                      <small>{formatTimeLabel(turn.created_at)}</small>
                    </div>
                    <div className="chat-bubble">
                      {turn.role === "assistant" ? (
                        <MarkdownMessage content={turn.content} />
                      ) : (
                        <>
                          <p className="chat-plain-text">{turn.content}</p>
                          {Array.isArray(turn.payload?.attachments)
                            ? renderAttachmentChips(turn.payload.attachments as ChatAttachment[])
                            : null}
                        </>
                      )}
                    </div>
                  </div>
                </li>
                {!showStreamingBubble && index === lastAssistantIndex
                  ? renderMapCard("agent-map-card-history", index + 1)
                  : null}
              </Fragment>
            ))}

            {showStreamStage ? (
              <li
                key="streaming-stage-status"
                className="chat-message assistant stream-event"
                style={{ animationDelay: `${Math.min(turnsForRender.length, 8) * 45}ms` }}
              >
                <div className="chat-message-stack chat-stage-stack">
                  <div className="chat-message-meta">
                    <span className="chat-message-role">执行阶段</span>
                    <small>{stageStatusMeta}</small>
                  </div>
                  <div className="chat-bubble chat-event-bubble">
                    <div className="chat-stage-live-head">
                      <span
                        className={`chat-stage-live-dot ${streamConnected || sending || awaitingAssistant ? "is-live" : ""}`}
                        aria-hidden="true"
                      />
                      <strong>{formatSubagentLabel(activeSubagent)}</strong>
                    </div>
                    <p>{stageStatusText}</p>
                    <small>流式阶段事件与最终回复会在这里衔接展示。</small>
                  </div>
                </div>
              </li>
            ) : null}

            {showStreamingBubble ? (
              <li
                key="streaming-assistant"
                className="chat-message assistant streaming"
                style={{ animationDelay: `${Math.min(turnsForRender.length, 8) * 45}ms` }}
              >
                <div className="chat-message-stack">
                  <div className="chat-message-meta">
                    <span className="chat-message-role">Arcadegent</span>
                    <small>{streamReplyActive ? "生成中..." : "已生成"}</small>
                  </div>
                  <div className="chat-bubble">
                    {streamReply.trim() ? (
                      <MarkdownMessage content={streamReply} className={streamReplyActive ? "is-streaming" : undefined} />
                    ) : (
                      <p className="chat-stream-placeholder">
                        正在生成回复...
                        {streamReplyActive ? <span className="chat-stream-caret" aria-hidden="true" /> : null}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            ) : null}

            {showStreamingBubble || lastAssistantIndex < 0
              ? renderMapCard("agent-map-card-streaming", turnsForRender.length + 1)
              : null}
          </ul>
        )}

        {loading ? <p className="chat-loading">加载会话中...</p> : null}
        <div ref={endRef} />
      </div>

      {error ? <div className="chat-error">{error}</div> : null}

      <form className="chat-composer" onSubmit={(event) => void onSubmit(event)}>
        <div className="chat-composer-tools">
          <button
            type="button"
            className="chat-upload-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={composerBusy}
          >
            上传文件或图片
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="chat-upload-input"
            accept=".md,.txt,.json,.jsonl,.pdf,.doc,.docx,image/*"
            multiple
            onChange={handleFilePick}
            disabled={composerBusy}
          />
        </div>
        {hasPendingAttachments ? renderAttachmentChips(pendingChatAttachments, { removable: true }) : null}
        <input
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="直接输入机厅、区域、路线，或带着文件和图片一起提问"
          disabled={composerBusy}
        />
        <button type="submit" disabled={composerBusy || (inputValue.trim().length === 0 && !hasPendingAttachments)}>
          {sending ? "发送中..." : awaitingAssistant ? "处理中..." : "发送"}
        </button>
        <div className="chat-composer-hint">
          支持把检索、路线、知识库问题和上传附件放在一次对话里一起提交。
        </div>
      </form>
    </div>
  );
}
