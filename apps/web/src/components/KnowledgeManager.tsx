import { useEffect, useMemo, useRef, useState } from "react";
import { deleteKnowledgeFile, deleteKnowledgeFilesBatch, getKnowledgeStatus, reindexKnowledge, uploadKnowledgeFile } from "../api/client";
import type { KnowledgeFileItem, KnowledgeStatus } from "../types";

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export function KnowledgeManager() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [deletingPath, setDeletingPath] = useState("");
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadStatus() {
    setLoading(true);
    setError("");
    try {
      const next = await getKnowledgeStatus();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载知识库状态失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    setSelectedPaths((prev) => prev.filter((item) => status?.files.some((file) => file.relative_path === item)));
  }, [status]);

  async function handleUpload(file: File | null) {
    if (!file) {
      return;
    }
    setUploading(true);
    setError("");
    setMessage("");
    try {
      const result = await uploadKnowledgeFile(file);
      setStatus(result.rag);
      setMessage(`已上传 ${result.file.name}，索引块数 ${result.rag.chunk_count}`);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleReindex() {
    setReindexing(true);
    setError("");
    setMessage("");
    try {
      const next = await reindexKnowledge();
      setStatus(next);
      setMessage(`索引已重建，当前块数 ${next.chunk_count}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重建索引失败");
    } finally {
      setReindexing(false);
    }
  }

  async function handleDelete(file: KnowledgeFileItem) {
    setDeletingPath(file.relative_path);
    setError("");
    setMessage("");
    try {
      await deleteKnowledgeFile(file.relative_path);
      const next = await getKnowledgeStatus();
      setStatus(next);
      setMessage(`已删除 ${file.name}，当前剩余 ${next.files.length} 个文件`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingPath("");
    }
  }

  async function handleBatchDelete() {
    if (!selectedPaths.length) {
      return;
    }
    setBatchDeleting(true);
    setError("");
    setMessage("");
    try {
      const next = await deleteKnowledgeFilesBatch(selectedPaths);
      const deletedCount = selectedPaths.length;
      setStatus(next);
      setSelectedPaths([]);
      setMessage(`已批量删除 ${deletedCount} 个文件，当前剩余 ${next.files.length} 个文件`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量删除失败");
    } finally {
      setBatchDeleting(false);
    }
  }

  function toggleSelected(relativePath: string, checked: boolean) {
    setSelectedPaths((prev) => {
      if (checked) {
        return prev.includes(relativePath) ? prev : [...prev, relativePath];
      }
      return prev.filter((item) => item !== relativePath);
    });
  }

  function toggleSelectAll(checked: boolean) {
    if (!status?.files.length) {
      setSelectedPaths([]);
      return;
    }
    setSelectedPaths(checked ? status.files.map((file) => file.relative_path) : []);
  }

  const allSelected = Boolean(status?.files.length) && selectedPaths.length === status?.files.length;
  const totalSize = useMemo(
    () => (status?.files ?? []).reduce((sum, file) => sum + file.size_bytes, 0),
    [status?.files]
  );
  const featureSummary = useMemo(() => {
    if (!status) {
      return "等待状态载入";
    }
    const features = [
      status.semantic_chunking_enabled ? "语义分块" : null,
      status.reranker_enabled ? "重排" : null,
      status.hybrid_search_enabled ? "混合检索" : null
    ].filter(Boolean);
    return features.length ? features.join(" / ") : "基础向量检索";
  }, [status]);
  const selectedSize = useMemo(() => {
    if (!status || !selectedPaths.length) {
      return 0;
    }
    const selectedSet = new Set(selectedPaths);
    return status.files.reduce((sum, file) => sum + (selectedSet.has(file.relative_path) ? file.size_bytes : 0), 0);
  }, [selectedPaths, status]);

  return (
    <section className="knowledge-shell">
      <div className="knowledge-hero browser-card">
        <small>Knowledge Base Control</small>
        <h2>把文档上传进知识库，然后立即让 RAG 识别。</h2>
        <p>支持 Markdown、TXT、JSON、JSONL、PDF、DOCX、DOC。上传成功后会自动重建索引。</p>
        <div className="knowledge-hero-meta">
          <span className="knowledge-hero-pill">{status ? `${status.files.length} 个文件` : "等待文件清单"}</span>
          <span className="knowledge-hero-pill">{status ? `${status.chunk_count} 个 Chunk` : "等待索引状态"}</span>
          <span className="knowledge-hero-pill">{status ? featureSummary : "等待能力状态"}</span>
        </div>
      </div>

      <div className="knowledge-grid">
        <div className="knowledge-panel browser-card">
          <div className="knowledge-section-head">
            <div className="knowledge-head-copy">
              <strong>知识库状态</strong>
              <small>查看索引健康度，并把新文档直接送进当前知识库。</small>
            </div>
            <button
              type="button"
              className="browser-secondary-btn"
              onClick={() => void loadStatus()}
              disabled={loading}
            >
              {loading ? "刷新中..." : "刷新状态"}
            </button>
          </div>

          {status ? (
            <div className="knowledge-stats">
              <div className="knowledge-stat">
                <span>目录</span>
                <strong>{status.directory}</strong>
                <small>当前知识源目录</small>
              </div>
              <div className="knowledge-stat">
                <span>索引状态</span>
                <strong>{status.index_ready ? "已就绪" : "未就绪"}</strong>
                <small>{status.enabled ? "RAG 已启用" : "RAG 当前未启用"}</small>
              </div>
              <div className="knowledge-stat">
                <span>Chunk 数量</span>
                <strong>{status.chunk_count}</strong>
                <small>上传或重建后实时更新</small>
              </div>
              <div className="knowledge-stat">
                <span>文件体量</span>
                <strong>{formatSize(totalSize)}</strong>
                <small>{status.files.length ? "当前文件累计大小" : "还没有入库文件"}</small>
              </div>
            </div>
          ) : null}

          {status ? (
            <div className="knowledge-status-strip">
              <div className="knowledge-status-pill">
                <span>支持格式</span>
                <strong>{status.supported_suffixes.join(" ")}</strong>
              </div>
              <div className="knowledge-status-pill">
                <span>检索能力</span>
                <strong>{featureSummary}</strong>
              </div>
            </div>
          ) : null}

          {status?.load_error ? <p className="knowledge-error">最近错误：{status.load_error}</p> : null}
          {error ? <p className="knowledge-error">{error}</p> : null}
          {message ? <p className="knowledge-success">{message}</p> : null}

          <div className="knowledge-actions">
            <label className="knowledge-upload">
              <input
                ref={inputRef}
                type="file"
                onChange={(event) => void handleUpload(event.target.files?.[0] ?? null)}
                disabled={uploading}
              />
              <span>{uploading ? "上传中..." : "选择并上传文件"}</span>
            </label>

            <button
              type="button"
              className="browser-primary-btn"
              onClick={() => void handleReindex()}
              disabled={reindexing}
            >
              {reindexing ? "重建中..." : "重建索引"}
            </button>
          </div>
        </div>

        <div className="knowledge-panel browser-card">
          <div className="knowledge-section-head">
            <div className="knowledge-file-heading">
              <strong>已识别文件</strong>
              <small>{status ? `${status.files.length} 个文件，支持批量整理` : ""}</small>
            </div>
            <div className="knowledge-toolbar">
              <label className="knowledge-select-all">
                <input
                  type="checkbox"
                  checked={allSelected}
                  disabled={!status?.files.length || batchDeleting}
                  onChange={(event) => toggleSelectAll(event.target.checked)}
                />
                <span>全选</span>
              </label>
              <button
                type="button"
                className="knowledge-delete-btn"
                onClick={() => void handleBatchDelete()}
                disabled={!selectedPaths.length || batchDeleting}
              >
                {batchDeleting ? "批量删除中..." : `批量删除所选${selectedPaths.length ? ` (${selectedPaths.length})` : ""}`}
              </button>
            </div>
          </div>

          {status?.files.length ? (
            <div className={`knowledge-selection-bar${selectedPaths.length ? " is-active" : ""}`}>
              <div className="knowledge-selection-copy">
                <strong>{selectedPaths.length ? `已选 ${selectedPaths.length} 个文件` : "尚未选择文件"}</strong>
                <small>
                  {selectedPaths.length
                    ? `预计操作体量 ${formatSize(selectedSize)}，可直接批量删除。`
                    : "可先勾选文件，再做批量删除整理。"}
                </small>
              </div>
              <span className="knowledge-selection-pill">
                {allSelected ? "已全选" : `${status.files.length} 个待管理`}
              </span>
            </div>
          ) : null}

          <div className="knowledge-file-list">
            {!status?.files.length ? (
              <div className="knowledge-empty-state">
                <strong>当前还没有知识库文件</strong>
                <p>先上传文档，系统会在完成后自动更新索引与文件清单。</p>
              </div>
            ) : null}
            {status?.files.map((file) => (
              <article key={file.relative_path} className="knowledge-file-item">
                <div className="knowledge-file-head">
                  <label className="knowledge-file-check">
                    <input
                      type="checkbox"
                      checked={selectedPaths.includes(file.relative_path)}
                      disabled={batchDeleting}
                      onChange={(event) => toggleSelected(file.relative_path, event.target.checked)}
                    />
                    <span className="sr-only">选择 {file.name}</span>
                  </label>
                  <div className="knowledge-file-copy">
                    <div className="knowledge-file-badges">
                      <span>{file.suffix}</span>
                      <span>{formatSize(file.size_bytes)}</span>
                    </div>
                    <strong>{file.name}</strong>
                    <p>{file.relative_path}</p>
                  </div>
                  <button
                    type="button"
                    className="knowledge-delete-btn"
                    onClick={() => void handleDelete(file)}
                    disabled={deletingPath === file.relative_path || batchDeleting}
                  >
                    {deletingPath === file.relative_path ? "删除中..." : "删除"}
                  </button>
                </div>
                <div className="knowledge-file-meta">
                  <span>{formatDate(file.updated_at)}</span>
                  <span>{selectedPaths.includes(file.relative_path) ? "已加入批量操作" : "单独可删除"}</span>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
