# Arcadegent RAG Evaluation

该目录提供可重复、可门禁、可比较的 RAG 测评系统。评测分为四层：

1. 检索质量：Hit、Precision、Recall@K、MRR@K、MAP@K、nDCG@K。
2. 上下文质量：关键事实是否出现在检索片段中。
3. 答案质量：必需事实、禁用断言、参考答案 Token F1、引用精确率/召回率、拒答准确率。
4. 运行质量：检索延迟、工具调用成功率、基线回归和阈值门禁。

默认指标是离线且确定性的，可以用于 CI。LLM Judge 是可选项，不默认参与阻断门禁。

## 快速运行

公开演示集不依赖私有数据或外部模型：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --dataset backend/evaluation/datasets/arcadegent_demo_v2.json \
  --source-path backend/evaluation/fixtures/knowledge \
  --embedding-model local-hash-v1 \
  --top-k 5 \
  --cutoffs 1,3,5 \
  --fail-on-gate
```

使用当前 `.env` 中的真实知识库和 embedding：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --dataset data/local/knowledge/eval_queries.json \
  --cold-cache \
  --fail-on-gate
```

每次运行会在 `data/runtime/rag-evaluation/` 生成完整 JSON 和摘要 Markdown。JSON 保留逐条检索结果、失败样本、数据集与知识语料 SHA-256、实验协议指纹、处理配置和运行环境，适合审计和二次分析。若数据集文件恰好放在知识目录中，评测运行会显式将其排除，避免标注答案泄漏进索引。

## 数据集规范

数据集使用版本化 JSON：

```json
{
  "name": "arcadegent-production",
  "version": "2.1.0",
  "cases": [
    {
      "id": "gamma_queue",
      "query": "Gamma Arcade 周末排队吗",
      "tags": ["review", "queue"],
      "relevant_documents": [
        {
          "title": "Gamma Arcade 评论摘录",
          "source_uri": "knowledge://shops/gamma",
          "relevance": 3
        }
      ],
      "expected_context_facts": [
        {
          "accepted": ["周末晚上排队会更明显", "周末晚间排队更多"],
          "contradictions": ["周末晚上完全不用排队"]
        }
      ],
      "reference_answer": "周末晚上排队更明显，建议错峰。",
      "required_answer_facts": ["周末晚上排队会更明显"],
      "forbidden_answer_claims": ["完全不用排队"]
    }
  ]
}
```

- `relevant_documents` 支持多个相关文档，`relevance` 用于 nDCG 分级相关性。
- 文档可用 `document_id/chunk_id`、`source_uri` 或 `title` 标识，优先使用稳定的 `source_uri`。
- `tags` 会自动形成切片报告，用于发现 FAQ、评论、长尾等类别的退化。
- `expected_no_answer=true` 用于无答案和拒答用例，此时可以不提供相关文档。
- 无答案样本只计入无答案准确率和误召回率，不会混入 Hit/MRR/MAP/nDCG。
- 事实可以是字符串，也可以用 `accepted` 提供等价表达、用 `contradictions` 阻止否定句造成词面误判。
- 原有 `expected_title`、`expected_snippet_substring` 格式保持兼容。

正式数据集应先通过 Schema 校验：

```bash
backend/.venv/bin/python backend/scripts/validate_rag_dataset.py path/to/dataset.json
backend/.venv/bin/python backend/scripts/validate_rag_dataset.py path/to/predictions.json --kind predictions
```

CLI 仍能加载旧版扁平数据集，但 Schema 和 CI 门禁要求 v2 格式，便于逐步迁移旧标注。

## 答案评测

传入离线生成的预测文件：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --predictions backend/evaluation/predictions.example.json
```

预测结构为 `id`、`answer` 和 `citations`。引用值应对应标注中的稳定文档标识。
存在预测文件时，默认门禁会要求预测覆盖率为 100%，并检查事实、禁用断言和引用指标。缺失预测或缺失标注不会自动获得满分。

也可以从本次真实检索上下文直接生成答案再评分：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --generate-answers \
  --answer-model your-answer-model \
  --fail-on-gate
```

生成器要求模型返回结构化 `answer/citations`，会记录完成率与生成延迟。该模式调用外部模型并产生费用，因此不进入默认 PR CI。

需要补充 LLM Judge 时显式开启，调用 `.env` 中的 OpenAI-compatible provider：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --predictions path/to/predictions.json \
  --llm-judge \
  --judge-model your-judge-model
```

Judge 输出 faithfulness、answer relevance、correctness。由于存在成本和模型波动，它不应替代确定性指标。

## 实验与门禁

`thresholds.json` 定义最小质量、最大延迟和需要监测的回归指标。对比候选配置时，先保存基线报告，再运行：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --hybrid \
  --baseline path/to/baseline.json \
  --max-regression 0.02 \
  --fail-on-gate
```

也可以生成独立的指标差异：

```bash
backend/.venv/bin/python backend/scripts/compare_rag_reports.py \
  path/to/baseline.json path/to/candidate.json \
  --output path/to/comparison.json
```

基线门禁要求 protocol fingerprint 完全一致，包括数据集、知识语料、Top-K、cutoff、缓存模式、性能采样次数与指标契约。Embedding、chunk、hybrid 和 reranker 属于允许变化的 treatment 配置，差异会单独记录。生产数据集应扩大到至少 200 条并由人工复核标注，不能把公开烟雾集数字作为业务结论。

稳定测量热查询延迟时，可先预热并重复采样：

```bash
backend/.venv/bin/python backend/scripts/evaluate_rag.py \
  --warmup-runs 2 \
  --latency-runs 20
```

`--cold-cache` 仅表示每次清理查询结果缓存，不等于重新构建索引；报告会明确记录缓存模式。索引构建成本应单独测量，不与在线检索 p95 混合。
