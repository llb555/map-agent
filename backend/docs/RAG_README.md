# RAG (Retrieval-Augmented Generation) 系统

Arcadegent的RAG系统支持基于知识库的智能检索，为Agent提供准确的背景知识支持。

## 🌟 特性

- ✅ **多种Embedding支持**：OpenAI API、Sentence Transformers、本地Hash
- ✅ **重排序（Reranker）**：两阶段检索提升精度
- ✅ **混合检索**：结合向量检索和BM25关键词检索
- ✅ **灵活配置**：支持多种模型和参数调优
- ✅ **完整评估**：内置评估脚本和指标

## 📁 文档目录

- **[RAG_RERANKER_GUIDE.md](./RAG_RERANKER_GUIDE.md)** - 重排序功能使用指南
- **[RAG_HYBRID_SEARCH_GUIDE.md](./RAG_HYBRID_SEARCH_GUIDE.md)** - 混合检索使用指南
- **[RAG_OPTIMIZATION_SUMMARY.md](./RAG_OPTIMIZATION_SUMMARY.md)** - 优化实施总结和性能对比

## 🚀 快速开始

### 1. 基础配置

在 `.env` 文件中添加：

```bash
# 启用RAG
RAG_ENABLED=true
RAG_SOURCE_PATH=data/local/knowledge
RAG_SEMANTIC_CHUNKING_ENABLED=false

# Embedding配置
RAG_EMBEDDING_MODEL=sentence-transformers:paraphrase-multilingual-MiniLM-L12-v2
```

### 2. 准备知识库

将知识文档放入 `data/local/knowledge/` 目录：

```
data/local/knowledge/
├── faq.json              # JSON格式FAQ
├── handbook.pdf          # PDF文档（按页抽取）
├── notes.docx            # Word 文档（正文/表格/页眉页脚/批注/文本框）
├── legacy.doc            # 老式 Word 文档（自动转换）
├── shop_comments.jsonl   # JSONL格式评论
└── guide.md              # Markdown文档
```

支持的格式：`.md`, `.txt`, `.json`, `.jsonl`, `.pdf`, `.docx`, `.doc`

PDF 说明：
- 基于 `pypdf` 抽取文本，默认按页进入知识库。
- 扫描版 PDF 如果本身没有可提取文本，当前不会自动 OCR。

Word 说明：
- `.docx` 会提取正文段落、表格、页眉、页脚、批注和文本框中的文本。
- `.doc` 会先自动转换为 `.docx`，再走同一套提取流程。
- `.doc` 自动转换优先使用 `soffice/libreoffice`，在 macOS 上也支持 `textutil` 作为后备。

### 3. 启动服务

```bash
cd backend
uvicorn app.main:app --reload
```

### 4. 测试检索

```bash
# 运行评估脚本
python scripts/evaluate_rag.py --dataset data/local/knowledge/eval_queries.json --top-k 4
```

## 🎯 推荐配置

### 开发/演示环境（无需下载模型）

```bash
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=local-hash-v1
```

### 生产环境（中文场景）

```bash
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=sentence-transformers:BAAI/bge-base-zh-v1.5
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base
```

### 高精度场景

```bash
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=sentence-transformers:BAAI/bge-large-zh-v1.5
RAG_SEMANTIC_CHUNKING_ENABLED=true
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-large
RAG_HYBRID_SEARCH_ENABLED=true
RAG_HYBRID_ALPHA=0.6
```

## 📊 性能指标

基于27个测试用例的评估结果：

| 配置 | Top-1准确率 | Hit@K准确率 | 片段匹配率 |
|------|------------|------------|-----------|
| 纯向量检索 | 81.48% | 92.59% | 88.89% |
| 混合检索(α=0.8) | 81.48% | 92.59% | 88.89% |
| 重排序（预期） | **~90%** | **~95%** | **~92%** |

## 🛠️ 核心功能

### 1. 重排序（Reranker）

两阶段检索策略：
1. 向量检索召回 top_k × 5 个候选
2. Cross-encoder模型重新排序，返回 top_k

**配置：**
```bash
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=sentence-transformers:BAAI/bge-reranker-base
RAG_RERANKER_TOP_K_MULTIPLIER=5
```

**预期效果：**
- 提升10-20% Top-1准确率
- 延迟增加：+50-100ms

详见：[RAG_RERANKER_GUIDE.md](./RAG_RERANKER_GUIDE.md)

### 2. 混合检索（Hybrid Search）

结合向量检索和BM25关键词检索：

```
final_score = alpha × vector_score + (1 - alpha) × bm25_score
```

**配置：**
```bash
RAG_HYBRID_SEARCH_ENABLED=true
RAG_HYBRID_ALPHA=0.5  # 0.0=纯BM25, 1.0=纯向量
```

**适用场景：**
- 大型知识库（>100文档）
- 需要精确匹配专有名词
- 技术文档、代码搜索

详见：[RAG_HYBRID_SEARCH_GUIDE.md](./RAG_HYBRID_SEARCH_GUIDE.md)

### 3. 多种Embedding模型

#### 远程API
```bash
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_BASE_URL=https://api.openai.com/v1
RAG_EMBEDDING_API_KEY=sk-...
```

#### 本地模型（推荐）
```bash
# 中文场景
RAG_EMBEDDING_MODEL=sentence-transformers:BAAI/bge-base-zh-v1.5

# 多语言
RAG_EMBEDDING_MODEL=sentence-transformers:paraphrase-multilingual-MiniLM-L12-v2

# 英文
RAG_EMBEDDING_MODEL=sentence-transformers:all-MiniLM-L6-v2
```

#### 本地Hash（无需下载）
```bash
RAG_EMBEDDING_MODEL=local-hash-v1
```

## 🔧 配置参数说明

### 基础配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RAG_ENABLED` | `false` | 是否启用RAG |
| `RAG_SOURCE_PATH` | `data/local/knowledge` | 知识库路径 |
| `RAG_CHUNK_SIZE` | `700` | 文档分块大小 |
| `RAG_CHUNK_OVERLAP` | `120` | 分块重叠字符数 |
| `RAG_SEMANTIC_CHUNKING_ENABLED` | `false` | 是否优先使用 SemanticChunker，失败时自动回退固定分块 |
| `RAG_TOP_K` | `4` | 返回结果数量 |

### Embedding配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RAG_EMBEDDING_MODEL` | `""` | Embedding模型名称 |
| `RAG_EMBEDDING_API_KEY` | `""` | API密钥（远程模型） |
| `RAG_EMBEDDING_BASE_URL` | `""` | API端点（远程模型） |
| `RAG_EMBEDDING_TIMEOUT_SECONDS` | `20` | 请求超时时间 |

### 重排序配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RAG_RERANKER_ENABLED` | `false` | 是否启用重排序 |
| `RAG_RERANKER_MODEL` | `""` | Reranker模型名称 |
| `RAG_RERANKER_TOP_K_MULTIPLIER` | `5` | 召回倍数 |
| `RAG_RERANKER_TIMEOUT_SECONDS` | `20` | 超时时间 |

### 混合检索配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RAG_HYBRID_SEARCH_ENABLED` | `false` | 是否启用混合检索 |
| `RAG_HYBRID_ALPHA` | `0.5` | 向量权重（0-1） |

## 📈 评估工具

### 运行评估

```bash
cd backend
python scripts/evaluate_rag.py --dataset data/local/knowledge/eval_queries.json --top-k 4
```

### 评估指标

- **Top-1准确率**：第一个结果命中率
- **Hit@K准确率**：前K个结果中包含正确答案的比例
- **片段匹配率**：返回片段包含期望内容的比例

### 对比测试

```bash
# 基线测试
RAG_RERANKER_ENABLED=false RAG_HYBRID_SEARCH_ENABLED=false python scripts/evaluate_rag.py

# 启用重排序
RAG_RERANKER_ENABLED=true python scripts/evaluate_rag.py

# 启用混合检索
RAG_HYBRID_SEARCH_ENABLED=true python scripts/evaluate_rag.py

# 全部启用
RAG_RERANKER_ENABLED=true RAG_HYBRID_SEARCH_ENABLED=true python scripts/evaluate_rag.py
```

## 🏗️ 架构说明

### 核心组件

```
LangChainRAGService
├── Embeddings
│   ├── OpenAICompatibleEmbeddings（远程API）
│   ├── SentenceTransformerEmbeddings（本地模型）
│   └── LocalHashEmbeddings（简单Hash）
├── Reranker
│   ├── SentenceTransformerReranker（Cross-encoder）
│   └── KeywordReranker（关键词fallback）
└── BM25Index（自实现BM25算法）
```

### 检索流程

```
用户查询
    ↓
[向量化]
    ↓
[检索策略选择]
    ├─ 纯向量检索
    └─ 混合检索（向量 + BM25）
    ↓
[召回候选]
    召回 top_k × multiplier 个文档
    ↓
[可选：重排序]
    Cross-encoder精排
    ↓
[返回结果]
    最终 top_k 个文档
```

## 🐛 故障排除

### 模型下载失败

```bash
# 手动下载Embedding模型
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-zh-v1.5')"

# 手动下载Reranker模型
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"
```

### 内存不足

- 使用更小的模型（MiniLM而非Large）
- 降低 `RAG_CHUNK_SIZE`
- 减少 `RAG_RERANKER_TOP_K_MULTIPLIER`

### 检索速度慢

- 禁用重排序：`RAG_RERANKER_ENABLED=false`
- 使用更快的模型：`all-MiniLM-L6-v2`
- 减少 `RAG_TOP_K`

### 检索结果不准确

- 启用重排序
- 调整 `RAG_HYBRID_ALPHA`
- 使用更好的Embedding模型
- 优化知识库内容质量

## 📚 API示例

### Health检查

```bash
curl http://localhost:8000/health
```

返回：
```json
{
  "rag": {
    "enabled": true,
    "embeddings_configured": true,
    "reranker_enabled": true,
    "reranker_configured": true,
    "hybrid_search_enabled": true,
    "bm25_configured": true,
    "index_ready": true,
    "chunk_count": 9
  }
}
```

### 使用知识搜索工具

知识搜索通过 `knowledge_search_tool` 自动集成到Agent中：

```python
# Agent会自动调用
result = tool_registry.execute(
    tool_name="knowledge_search_tool",
    arguments={"query": "Gamma Arcade 评论怎么样", "top_k": 4}
)
```

## 🔮 未来优化方向

1. **向量数据库集成**（知识库>500文档时）
   - FAISS（快速，本地）
   - Chroma（轻量级）
   - Qdrant（功能丰富）

2. **查询优化**
   - Query改写/扩展
   - HyDE（假设文档生成）
   - 多查询检索

3. **上下文优化**
   - 智能摘要
   - 上下文压缩
   - 相关性过滤

4. **缓存机制**
   - 查询缓存
   - Embedding缓存
   - 持久化存储

## 🤝 贡献

欢迎提交Issue和Pull Request改进RAG系统！

## 📄 许可

MIT License
