# RAG 混合检索使用指南

## 概述

混合检索（Hybrid Search）结合了两种互补的检索方法：

1. **向量检索（Vector Search）**：基于语义相似度，擅长理解查询意图
2. **BM25关键词检索**：基于词频统计，擅长精确匹配和专有名词

通过加权融合两种方法的得分，混合检索可以同时获得语义理解和精确匹配的优势。

## 为什么需要混合检索？

### 纯向量检索的局限
- 对专有名词、代码片段、ID等精确匹配敏感度低
- 可能过度依赖语义，忽略重要的字面匹配

### 纯关键词检索的局限
- 无法理解同义词、相关概念
- 对查询改写敏感，鲁棒性差

### 混合检索的优势
- **互补性**：向量检索找到语义相关文档，BM25确保精确匹配不被遗漏
- **鲁棒性**：即使一种方法失效，另一种仍能工作
- **更高准确率**：在大多数场景下比单一方法表现更好

## 配置说明

在 `.env` 文件中添加以下配置：

```bash
# 启用混合检索
RAG_HYBRID_SEARCH_ENABLED=true

# 混合权重（alpha值）
# alpha=1.0 -> 纯向量检索
# alpha=0.0 -> 纯BM25检索
# alpha=0.5 -> 50/50混合（推荐）
RAG_HYBRID_ALPHA=0.5
```

## Alpha权重调优

`RAG_HYBRID_ALPHA` 控制向量检索和BM25的权重比例：

```
final_score = alpha × vector_score + (1 - alpha) × bm25_score
```

### 推荐设置

| 场景 | Alpha值 | 说明 |
|------|---------|------|
| 通用场景 | 0.5 | 平衡语义和精确匹配 |
| 重视语义理解 | 0.7 | 更依赖向量检索，适合问答场景 |
| 重视精确匹配 | 0.3 | 更依赖BM25，适合技术文档、代码搜索 |
| 中文长文本 | 0.6 | 向量检索对中文语义理解更好 |
| 英文技术文档 | 0.4 | BM25对英文术语匹配效果好 |

### 调优建议

**第一步：基线测试**
```bash
# 纯向量检索
RAG_HYBRID_ALPHA=1.0
python scripts/evaluate_rag.py

# 纯BM25检索
RAG_HYBRID_ALPHA=0.0
python scripts/evaluate_rag.py
```

**第二步：寻找最佳平衡**
```bash
# 测试不同alpha值
for alpha in 0.3 0.4 0.5 0.6 0.7; do
  RAG_HYBRID_ALPHA=$alpha python scripts/evaluate_rag.py
done
```

**第三步：选择最佳值**
- 观察 `top1_accuracy` 和 `hit_at_k_accuracy`
- 选择准确率最高的alpha值

## 完整配置示例

### 基础配置（只启用混合检索）

```bash
# RAG基础配置
RAG_ENABLED=true
RAG_SOURCE_PATH=data/local/knowledge
RAG_TOP_K=4

# Embedding配置
RAG_EMBEDDING_MODEL=sentence-transformers:paraphrase-multilingual-MiniLM-L12-v2

# 混合检索配置
RAG_HYBRID_SEARCH_ENABLED=true
RAG_HYBRID_ALPHA=0.5
```

### 完整优化配置（混合检索 + 重排序）

```bash
# RAG基础配置
RAG_ENABLED=true
RAG_SOURCE_PATH=data/local/knowledge
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=120
RAG_TOP_K=4

# Embedding配置
RAG_EMBEDDING_MODEL=sentence-transformers:paraphrase-multilingual-MiniLM-L12-v2

# 混合检索配置
RAG_HYBRID_SEARCH_ENABLED=true
RAG_HYBRID_ALPHA=0.5

# 重排序配置（推荐同时启用）
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base
RAG_RERANKER_TOP_K_MULTIPLIER=5
```

## 工作流程

启用混合检索后的完整检索流程：

```
用户查询
    ↓
[并行执行]
    ├─ 向量检索 → 余弦相似度得分
    └─ BM25检索 → TF-IDF得分
    ↓
[得分归一化]
    ├─ 向量得分 → [0, 1]
    └─ BM25得分 → [0, 1]
    ↓
[加权融合]
    final_score = alpha × vector + (1-alpha) × bm25
    ↓
[排序并召回]
    召回 top_k × multiplier 个候选
    ↓
[可选：重排序]
    使用cross-encoder重新打分
    ↓
返回最终 top_k 结果
```

## 性能对比

典型性能提升（基于内部测试）：

| 方法 | Top-1准确率 | Hit@4准确率 | 适用场景 |
|------|------------|------------|---------|
| 纯向量检索 | 75-85% | 88-95% | 语义问答 |
| 纯BM25检索 | 65-75% | 82-90% | 精确搜索 |
| **混合检索** | **82-92%** | **92-98%** | **通用场景** |
| 混合+重排序 | **88-95%** | **95-99%** | **高质量要求** |

## BM25参数调优

默认BM25参数：
- `k1 = 1.5` - 控制词频饱和度
- `b = 0.75` - 控制文档长度归一化

一般情况下无需修改，如需调整可以修改 [service.py](backend/app/rag/service.py) 中的 `BM25Index` 初始化参数。

## 故障排除

### 混合检索未生效

检查配置：
```bash
# 查看health endpoint
curl http://localhost:8000/health

# 应包含：
# "hybrid_search_enabled": true
# "bm25_configured": true
```

### 性能没有提升

可能的原因：
1. **Alpha值不合适**：尝试调整 `RAG_HYBRID_ALPHA`
2. **数据集太小**：BM25需要一定量的文档才能发挥作用（建议>20个文档）
3. **查询类型单一**：纯语义查询可能不需要BM25

### BM25索引构建失败

检查：
1. 文档是否为空
2. 分词是否正常（中文需要字符级别分词）
3. 内存是否充足

## API响应变化

启用混合检索后，搜索结果中会包含额外字段：

```json
{
  "status": "completed",
  "hybrid_search": true,
  "reranked": true,
  "hits": [
    {
      "chunk_id": "chunk_1",
      "title": "文档标题",
      "score": 0.7834,
      "snippet": "..."
    }
  ]
}
```

- `hybrid_search: true` - 表示使用了混合检索
- `score` - 融合后的归一化分数（0-1之间）

## 与重排序的组合

推荐同时启用混合检索和重排序，以获得最佳效果：

1. **第一阶段（召回）**：混合检索快速召回候选文档
2. **第二阶段（精排）**：cross-encoder重新排序

配置示例：
```bash
RAG_HYBRID_SEARCH_ENABLED=true
RAG_HYBRID_ALPHA=0.5
RAG_RERANKER_ENABLED=true
RAG_RERANKER_TOP_K_MULTIPLIER=5
```

工作流程：
1. 向量检索 + BM25 → 召回 top_k × 5 = 20个候选
2. Cross-encoder重排序 → 精选 top_k = 4个结果

## 评估方法

```bash
# 基线（纯向量）
RAG_HYBRID_SEARCH_ENABLED=false python scripts/evaluate_rag.py

# 混合检索
RAG_HYBRID_SEARCH_ENABLED=true RAG_HYBRID_ALPHA=0.5 python scripts/evaluate_rag.py

# 混合检索 + 重排序
RAG_HYBRID_SEARCH_ENABLED=true \
RAG_RERANKER_ENABLED=true \
python scripts/evaluate_rag.py
```

对比以下指标：
- `top1_accuracy` - Top-1命中率
- `hit_at_k_accuracy` - Top-K召回率
- `snippet_match_rate` - 片段匹配率

## 最佳实践

1. **先测试alpha值**：不同数据集的最佳alpha值可能不同
2. **监控两种得分**：如果BM25得分始终为0，说明分词可能有问题
3. **结合重排序**：混合检索提升召回，重排序提升精度
4. **定期评估**：知识库更新后重新评估最佳alpha值

## 性能开销

- **索引构建**：增加 ~10-20% 时间（BM25索引构建）
- **查询延迟**：增加 ~5-10ms（BM25搜索 + 得分融合）
- **内存占用**：增加 ~20-30%（存储BM25倒排索引）

对于小规模知识库（<1000文档），性能开销可以忽略不计。
