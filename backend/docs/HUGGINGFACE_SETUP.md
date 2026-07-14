# Hugging Face 配置

Arcadegent 使用 `sentence-transformers` 在本地运行 Hugging Face embedding 和 reranker，不会把知识文本发送给 Hugging Face。首次使用需要从 Hub 下载模型，后续可以只读本地缓存运行。

## 推荐配置

中文检索的起步配置：

```dotenv
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=sentence-transformers:BAAI/bge-small-zh-v1.5
RAG_VECTOR_BACKEND=faiss

RAG_RERANKER_ENABLED=false
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base

HF_TOKEN=
HUGGINGFACE_CACHE_DIR=data/runtime/huggingface
HF_HUB_OFFLINE=false
HUGGINGFACE_DEVICE=
HUGGINGFACE_TRUST_REMOTE_CODE=false
HUGGINGFACE_REVISION=
```

`bge-small-zh-v1.5` 适合先建立质量基线。确认召回质量和延迟后，再用测评系统判断是否启用 reranker。

## Token

公共模型无需 Token。私有或需要同意许可的 gated 模型才需要：

```dotenv
HF_TOKEN=hf_your_read_only_token
```

Token 只写入未提交的根目录 `.env`。不要写入示例文件、Dockerfile、命令行参数、GitHub 日志或评测报告。建议创建只读、用途受限的 Token。

## 下载并验证

配置 `.env` 后，从仓库根目录执行：

```bash
backend/.venv/bin/python backend/scripts/verify_huggingface_models.py \
  --embedding-model sentence-transformers:BAAI/bge-small-zh-v1.5
```

同时验证 reranker：

```bash
backend/.venv/bin/python backend/scripts/verify_huggingface_models.py \
  --embedding-model sentence-transformers:BAAI/bge-small-zh-v1.5 \
  --reranker-model sentence-transformers:BAAI/bge-reranker-base
```

下载完成后验证纯离线启动：

```bash
backend/.venv/bin/python backend/scripts/verify_huggingface_models.py \
  --embedding-model sentence-transformers:BAAI/bge-small-zh-v1.5 \
  --offline
```

如果离线验证失败，说明缓存不完整、revision 不匹配或缓存路径发生了变化。

## 使用真实模型测评

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --dataset data/local/knowledge/eval_queries.json \
  --embedding-model sentence-transformers:BAAI/bge-small-zh-v1.5 \
  --cold-cache \
  --latency-runs 10 \
  --fail-on-gate
```

启用重排序进行候选实验：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --dataset data/local/knowledge/eval_queries.json \
  --embedding-model sentence-transformers:BAAI/bge-small-zh-v1.5 \
  --reranker sentence-transformers:BAAI/bge-reranker-base \
  --baseline path/to/embedding-only-report.json \
  --fail-on-gate
```

模型名称、revision、chunk 参数和 reranker 配置会进入评测 treatment fingerprint。数据集、语料或评测协议不一致时，系统会拒绝错误的基线对比。

## Docker

Compose 会把宿主机 `data/` 挂载到容器 `/app/data`，模型缓存固定为 `/app/data/huggingface`。容器重建后无需重新下载模型。

首次下载需要容器能够访问 Hugging Face Hub。生产发布时建议预热缓存，然后设置：

```dotenv
HF_HUB_OFFLINE=true
```

不要把模型缓存提交到 Git。完全离线交付应使用受控构建流程制作预置模型镜像，或挂载只读模型卷。

## 常见问题

- `sentence_transformer_load_failed:...:offline`：离线缓存缺失，先关闭 `HF_HUB_OFFLINE` 下载。
- `401/403`：模型需要许可或 Token 权限不足。
- 下载反复发生：确认本地和 Docker 使用相同的 `HUGGINGFACE_CACHE_DIR/HF_HOME`。
- CPU 延迟较高：先用 small 模型，减少 reranker 候选数，再依据 p95 和质量指标决定是否升级硬件。
- `trust_remote_code` 报错：默认保持关闭；只有经过代码审查后才允许执行模型仓库的自定义代码。

## 当前基准

2026-07-14 使用 `BAAI/bge-small-zh-v1.5`、FAISS、Top-5，在 27 条本地标注查询和 14 个知识 Chunk 上进行三次冷查询缓存采样：

| 指标 | 结果 |
|---|---:|
| Hit@1 | 70.37% |
| Hit@3 | 85.19% |
| Hit@5 | 92.59% |
| MRR@5 | 79.01% |
| nDCG@5 | 82.42% |
| 上下文事实召回 | 88.89% |
| 查询 p95 | 13.51 ms |

同一数据集此前使用 `local-hash-v1` 时 Hit@1 为 55.56%、Hit@5 为 85.19%、MRR@5 为 65.06%。真实 BGE 模型分别提升约 14.81、7.40 和 13.95 个百分点。

该结果只说明当前小规模本地标注集上的离线表现，不代表生产流量效果。扩大到 200 条以上人工复核数据后，才能作为稳定的业务质量结论。
