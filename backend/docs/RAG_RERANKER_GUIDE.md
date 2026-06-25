# RAG Reranker 使用指南

## 概述

重排序（Reranking）是一种两阶段检索策略，可以显著提升RAG的检索准确率：

1. **第一阶段（召回）**：使用向量检索快速召回较多候选文档（如 top_k × 5）
2. **第二阶段（精排）**：使用更精确的cross-encoder模型对候选文档重新排序，返回最终的top_k结果

## 为什么需要重排序？

- **向量检索的局限性**：单纯的余弦相似度可能无法准确捕捉查询和文档的语义相关性
- **精度提升**：Cross-encoder能够同时处理查询和文档，计算更精确的相关性分数
- **效果显著**：通常可以提升10-20%的检索准确率

## 配置说明

在 `.env` 文件中添加以下配置：

```bash
# 启用重排序
RAG_RERANKER_ENABLED=true

# Reranker模型配置
# 格式：sentence-transformers:<model_name>
RAG_RERANKER_MODEL=sentence-transformers:cross-encoder/ms-marco-MiniLM-L-6-v2

# 召回候选数倍数（召回 top_k × multiplier 个候选）
RAG_RERANKER_TOP_K_MULTIPLIER=5

# 重排序超时时间（秒）
RAG_RERANKER_TIMEOUT_SECONDS=20
```

## 推荐的Reranker模型

### 1. 英文场景
```bash
# 快速但准确（推荐）
RAG_RERANKER_MODEL=sentence-transformers:cross-encoder/ms-marco-MiniLM-L-6-v2

# 更高精度（稍慢）
RAG_RERANKER_MODEL=sentence-transformers:cross-encoder/ms-marco-TinyBERT-L-6
```

### 2. 中文场景
```bash
# 中文优化的reranker（推荐）
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base

# 更大的模型（更准确）
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-large
```

### 3. 多语言场景
```bash
# 支持多语言
RAG_RERANKER_MODEL=sentence-transformers:cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
```

## 使用示例

### 完整配置示例

```bash
# 基础RAG配置
RAG_ENABLED=true
RAG_SOURCE_PATH=data/local/knowledge
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=120
RAG_TOP_K=4

# Embedding配置
RAG_EMBEDDING_MODEL=sentence-transformers:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# 重排序配置（新增）
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base
RAG_RERANKER_TOP_K_MULTIPLIER=5
```

### 检索流程

启用重排序后，检索流程如下：

1. 用户请求 `top_k=4`
2. 系统先召回 `4 × 5 = 20` 个候选文档（使用向量相似度）
3. Cross-encoder对这20个文档重新打分
4. 返回重排序后的top 4结果

## 性能调优

### 调整召回倍数

```bash
# 更保守（更快，可能准确率略低）
RAG_RERANKER_TOP_K_MULTIPLIER=3

# 默认推荐
RAG_RERANKER_TOP_K_MULTIPLIER=5

# 更激进（更慢，可能准确率更高）
RAG_RERANKER_TOP_K_MULTIPLIER=10
```

### 选择合适的模型

| 场景 | 推荐模型 | 速度 | 准确率 |
|------|---------|------|--------|
| 英文，追求速度 | ms-marco-MiniLM-L-6-v2 | ⚡⚡⚡ | ⭐⭐⭐ |
| 中文，平衡 | BAAI/bge-reranker-base | ⚡⚡ | ⭐⭐⭐⭐ |
| 中文，高精度 | BAAI/bge-reranker-large | ⚡ | ⭐⭐⭐⭐⭐ |

## 效果评估

使用评估脚本验证重排序效果：

```bash
# 不启用重排序
RAG_RERANKER_ENABLED=false python backend/scripts/evaluate_rag.py

# 启用重排序
RAG_RERANKER_ENABLED=true python backend/scripts/evaluate_rag.py
```

对比以下指标：
- `top1_accuracy` - Top-1准确率
- `hit_at_k_accuracy` - Hit@K准确率
- `snippet_match_rate` - 片段匹配率

## 故障排除

### 模型下载失败

首次使用会自动下载模型，如果下载失败：

```bash
# 手动下载模型
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
```

### 内存不足

如果遇到内存问题，尝试：
1. 使用更小的模型（如 MiniLM 而非 Large）
2. 降低 `RAG_RERANKER_TOP_K_MULTIPLIER`
3. 减少 `RAG_TOP_K`

### 速度太慢

如果重排序太慢：
1. 使用更快的模型（如 MiniLM-L-6）
2. 降低召回倍数到 3
3. 考虑只在关键查询时启用重排序

## 降级策略

系统内置了自动降级机制：
- 如果reranker初始化失败，自动降级到关键词重排序
- 如果重排序过程出错，自动返回原始向量检索结果
- 降级信息会在搜索结果的 `reranker_error` 字段中返回

## API响应变化

启用重排序后，搜索结果中会包含额外字段：

```json
{
  "status": "completed",
  "reranked": true,
  "hits": [
    {
      "chunk_id": "chunk_1",
      "title": "文档标题",
      "score": 0.8921,
      "snippet": "...",
      "reranked": true
    }
  ]
}
```

- `reranked: true` - 表示结果经过重排序
- 每个hit的 `score` - 重排序后的分数（范围通常在-10到10之间）
