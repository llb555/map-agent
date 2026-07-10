
# Arcadegent 面试回答稿

日期：2026-07-08

这份文档把今天窗口里问到的问题整理成面试时更好讲的版本。每个问题都按“先一句话回答，再展开两三层细节”的方式写，方便直接背，也方便现场根据面试官追问取舍。

## 1. 项目整体怎么介绍

可以这样回答：

Arcadegent 是一个面向音游玩家的机厅搜索、附近推荐和路线规划应用。它不是普通聊天机器人，而是一个业务型 Agent：用户用自然语言提问后，后端会判断意图，调用搜索、定位、路线规划或知识库检索工具，把结构化结果写进 working memory，最后生成回答，并通过 SSE 把执行过程实时推给前端。

如果展开讲，我会分成三层：

第一层是前端。前端用 React、TypeScript、Vite 和 Zustand，负责聊天界面、机厅列表、地图路线和流式状态展示。

第二层是后端。后端用 FastAPI，提供聊天会话、知识库、机厅查询、定位解析和 SSE 流式接口。

第三层是 Agent Runtime。项目没有直接把所有逻辑塞进一个 prompt，而是用自研 ReAct Runtime 串起 main_agent、search_worker、navigation_worker 和工具注册表。这样搜索、导航、知识检索这些任务边界更清楚，也更容易调试。

可以补一句：

这个项目的重点不是让模型“凭空回答”，而是让模型调工具、读结构化上下文，再把结果组织成用户能看懂的回复。

## 2. 有做上下文压缩吗

可以这样回答：

项目没有做严格意义上的语义摘要式上下文压缩，也没有实现 token-aware compressor。现在做的是轻量上下文控制：限制最近对话轮数、把工具结果结构化放进 working memory、RAG 只注入少量相关片段。

具体来说有几块：

- `AGENT_CONTEXT_WINDOW=24`，只保留最近若干条 turn history 进模型上下文。
- `ContextBuilder` 会把 working memory 整理成 `runtime state` 和 `context_payload`，而不是把所有原始工具输出都塞进 prompt。
- RAG 默认只召回 `RAG_TOP_K=4` 个片段。
- RAG 文档切块默认是 `RAG_CHUNK_SIZE=700`、`RAG_CHUNK_OVERLAP=120`。

所以我会说：项目做了上下文裁剪和结构化组织，但还没做到自动摘要压缩。后续如果要增强，可以加一层 token 统计和会话摘要，把旧 turn 压成长期摘要，只保留最近几轮原文。

## 3. 多路召回和混合检索怎么实现

可以这样回答：

项目实现的是 RAG 内部的轻量多路召回，主要是向量召回加 BM25 关键词召回。两路召回各自打分，然后把分数归一化，再按权重融合。

流程是：

```text
用户 query
  -> 生成 query embedding
  -> 向量检索，走 memory 或 FAISS
  -> BM25 关键词检索
  -> 两路分数归一化到 0 到 1
  -> 按 alpha 加权融合
  -> 排序取 TopK
  -> 可选 reranker 精排
```

融合公式是：

```text
final_score = alpha * vector_score + (1 - alpha) * bm25_score
```

配置上：

```text
RAG_HYBRID_SEARCH_ENABLED=false
RAG_HYBRID_ALPHA=0.5
RAG_RERANKER_TOP_K_MULTIPLIER=5
```

如果开启 reranker，系统会先召回更多候选，比如最终要 4 条结果，就先召回 `4 * 5 = 20` 条，再用 CrossEncoder 或关键词 reranker 精排。

我会特别说明一点：这不是完整的通用多召回框架。现在的多路主要是 RAG 里的 dense vector + sparse BM25 两路融合，还没有做标题召回、标签召回、图谱召回、用户行为召回这种可插拔 recall router。

## 4. 已经实现 LangChain 或 LangGraph 了吗

可以这样回答：

项目用了 LangChain，但没有用 LangGraph。

LangChain 主要用在 RAG 文档处理这一层，比如：

- `Document` 文档对象。
- `RecursiveCharacterTextSplitter` 固定切块。
- 可选 `SemanticChunker` 语义切块。

Agent 编排没有用 LangGraph，而是项目自己实现了一套轻量 ReAct Runtime。原因是这个项目的业务链路比较明确，需要和 SSE、working memory、工具权限、地图 artifacts 强绑定。自研 Runtime 更容易控制事件流、工具回填和前端展示。

可以补一句：

如果后续 Agent 状态越来越复杂，比如出现更多分支、回滚、并行节点和可视化 DAG，再考虑引入 LangGraph 会更合适。现在的自研 runtime 足够覆盖 main_agent 调 worker 的场景。

## 5. Working memory 是怎么设计的

可以这样回答：

working memory 是会话级的结构化状态，用来保存工具结果和中间产物。它和聊天 history 不一样：history 是给模型看的自然语言过程，working memory 是程序可读、可复用的业务状态。

它在 `AgentSessionState` 里，核心结构是：

```text
working_memory
  ├─ artifacts
  └─ worker_runs
```

里面会保存：

- `shops`：搜索到的机厅列表。
- `shop`：当前选中的机厅。
- `total`：结果总数。
- `route`：路线规划结果。
- `destination`：导航目的地。
- `client_location`：浏览器定位和逆地理结果。
- `resolved_locations`：地点解析结果。
- `knowledge_hits`：知识库命中片段。
- `view_payload`：地图展示需要的数据。
- `query_rewrite`：查询改写结果。
- `tool_trace`：工具执行轨迹。

举个例子：用户第一轮问“附近有哪些机厅”，搜索结果会写进 `shops`。下一轮用户说“帮我导航到第一个”，系统就可以直接从 `shops[0]` 取目标，再调用路线工具，而不是让模型从自然语言回答里猜“第一个”是哪家。

这个设计的好处是多轮任务更稳，也更省 token。

## 6. SSE 是怎么实现的

可以这样回答：

项目的 SSE 是后端单向推送 Agent 执行过程。前端先创建聊天会话，后端异步跑 Agent，然后前端用 `EventSource` 订阅 `/api/stream/{session_id}`。

后端用 FastAPI 的 `StreamingResponse`：

```text
GET /api/stream/{session_id}
media_type = text/event-stream
```

每个事件都有：

```text
id
event
data
```

常见事件包括：

- `session.started`
- `subagent.changed`
- `worker.started`
- `tool.started`
- `assistant.token`
- `navigation.route_ready`
- `assistant.completed`
- `session.failed`

项目里还有一个 `ReplayBuffer`。它会按 session 保存最近的事件，前端断线重连时可以带 `Last-Event-ID` 或 `last_event_id`，后端只补发漏掉的事件。没有新事件时，后端发 `: keep-alive` 保持连接。

为什么用 SSE 而不是 WebSocket：

这个场景主要是后端把 Agent 状态、工具执行和 token 输出推给前端，方向比较单一，不需要复杂双向通信。SSE 更轻，浏览器原生支持，断线重连也自然。WebSocket 更适合协同编辑、实时游戏、多端双向通信，这里用它反而重了。

## 7. 多 Agent 是怎么串联的

可以这样回答：

项目是 main_agent 加 worker 的结构。main_agent 负责理解用户意图和调度，worker 负责具体执行。

链路是：

```text
main_agent
  -> invoke_worker
  -> search_worker 或 navigation_worker
  -> worker 调工具
  -> 工具结果写入 worker memory
  -> worker 结果合并回父会话 working memory
  -> main_agent 生成最终回复
```

角色分工是：

- `main_agent`：判断用户是搜索、附近推荐、导航还是知识问答，并组织最终回答。
- `search_worker`：做机厅搜索、附近推荐、知识库 fallback。
- `navigation_worker`：做地点解析、目的地选择和路线规划。

每个 subagent 都有自己的 prompt、allowed tools 和 skill files。比如 search_worker 不需要路线规划工具，navigation_worker 才需要 route_plan_tool。这样可以减少工具误用，也让 prompt 更聚焦。

执行过程中，后端会通过 SSE 发 `subagent.changed`、`worker.started` 等事件，前端就能显示当前走到哪个阶段。

## 8. 前后端跨域怎么解决

可以这样回答：

开发环境主要靠 Vite proxy，后端也配置了 CORS。

前端 Vite 配置：

```text
/api    -> http://127.0.0.1:8000
/health -> http://127.0.0.1:8000
```

这样浏览器请求看起来是打到前端同源地址，再由 Vite 转发到后端，开发时基本不会被 CORS 卡住。

后端 FastAPI 也加了 `CORSMiddleware`：

```text
allow_origins = CORS_ALLOW_ORIGINS
allow_credentials = true
allow_methods = ["*"]
allow_headers = ["*"]
```

生产环境可以走两种方式：一种是 Nginx 把前后端反代到同源；另一种是后端把前端域名加入 CORS 白名单。

## 9. 上下文窗口总 token 多大，为什么这么选

可以这样回答：

项目没有显式定义“总上下文窗口 token 数”，也没有做精确 token 计数。它主要通过几组参数间接控制上下文大小。

关键配置是：

```text
AGENT_CONTEXT_WINDOW=24
LLM max_tokens=500
RAG_TOP_K=4
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=120
```

解释一下：

- `AGENT_CONTEXT_WINDOW=24` 控制最近多少条 turn history 会进入模型。
- LLM 默认输出 `max_tokens=500`，避免单次回答太长。
- RAG 默认只注入 4 个片段，每个 chunk 大约 700 字符。

为什么这么选：

这个项目的问题大多是搜索、导航和机厅信息问答，真正关键的是当前请求、最近几轮对话和 working memory 里的结构化结果，不需要把完整历史全部塞进去。这样可以兼顾稳定性、延迟和成本。

如果面试官追问不足，我会说：目前缺少 token-aware 裁剪，这是可以继续优化的点。后续可以加 tokenizer 统计，把 system prompt、history、tool results、RAG chunks 都放到统一预算里动态裁剪。

## 10. 整个链路怎么运转

可以这样回答：

一次完整请求大概是这样：

```text
1. 用户在前端输入问题
2. 前端调用 POST /api/chat/sessions 创建或复用 session
3. 后端 Orchestrator 开一个后台任务，先把 session_id 返回给前端
4. 前端用 EventSource 订阅 /api/stream/{session_id}
5. ReactRuntime 初始化 session state 和 working memory
6. ContextBuilder 拼 system prompt、subagent prompt、skill、runtime state
7. main_agent 调 LLM
8. 如果 LLM 返回 tool call，ToolRegistry 做 schema 校验、权限检查和执行
9. 如果需要 worker，main_agent 调 invoke_worker 切到 search_worker 或 navigation_worker
10. worker 调 db_query、geo_resolve、route_plan、knowledge_search 等工具
11. 工具结果写回 working memory
12. 后端持续通过 SSE 推送阶段事件、工具事件和 token
13. main_agent 基于 worker 结果生成最终回答
14. 前端收到 assistant.completed 后结束流，并刷新会话状态和地图展示
```

我会强调：这条链路的关键是“异步会话 + SSE + working memory”。异步会话保证长任务不会阻塞 HTTP 请求，SSE 让过程可见，working memory 让多轮任务能接上。

## 11. 有 skill 分层体系吗

可以这样回答：

有，但它是轻量的 prompt skill 分层，不是复杂技能市场。

项目里的 skill 文件主要放在：

```text
backend/app/agent/context/skills/
```

当前有：

- `search_result_reading.md`
- `navigation_result_reading.md`
- `response_composition.md`

这些 skill 不是固定回答模板，而是告诉模型怎么读结构化上下文。比如搜索结果里哪些字段优先看，导航结果里路线、目的地、交通信息怎么组织，最终回答要避免编造。

不同 subagent 可以挂不同 skill：

- search_worker 主要挂搜索结果读取 skill。
- navigation_worker 会同时挂搜索和导航结果读取 skill。

这样做的好处是：工具返回结构化 JSON 后，模型不会乱读字段，也不会把次要字段当成主结论。

## 12. 有 skill 沉淀机制吗

可以这样回答：

目前没有自动化 skill 沉淀机制。现在是人工维护 skill markdown，再通过 subagent profile 或 YAML overlay 挂到对应 agent 上。

也就是说，项目有 skill 分层和人工沉淀入口，但还没有形成闭环：

- 不会自动从历史任务总结 skill。
- 不会自动评估 skill 效果。
- 不会自动版本化上线。
- 没有 skill marketplace 或动态 skill registry。

如果要继续做，我会把它设计成：线上失败案例或高频任务先进入评审队列，然后人工或半自动总结成 skill，再通过回归集验证，最后挂到对应 worker。

## 13. 项目用了哪些框架，为什么这么选

可以这样回答：

后端主要是 FastAPI、Pydantic、Uvicorn、httpx、LangChain、FAISS、sentence-transformers、PyYAML 和 jsonschema。

前端主要是 React、TypeScript、Vite、Zustand、EventSource 和高德地图 SDK。

选型理由可以这样讲：

FastAPI 适合做异步 API 和 SSE，Pydantic 适合定义请求响应协议，整个后端类型比较清楚。

React 和 TypeScript 适合做复杂交互页面，Zustand 比 Redux 更轻，管理聊天状态、地图状态、流式回复状态比较舒服。

Vite 的开发体验好，而且 dev proxy 可以顺手解决本地跨域。

RAG 这块用了 LangChain 的文档和切分能力，但没有把 Agent 编排也绑定到 LangChain。这样既复用了成熟组件，又保留了自研 Runtime 对业务流程的控制。

FAISS 是为了让向量索引能本地持久化。早期 memory backend 更像 demo，FAISS 能减少重启后重复构建，也更接近真实工程使用。

## 14. Embedding 模型结构是什么，输出向量维度是多少

可以这样回答：

项目支持三种 embedding 方式。

第一种是 `local-hash-v1`。这是内置 hash embedding，默认 256 维。它不是神经网络模型，而是把 token hash 到固定维度，再做归一化。优点是本地可跑、无依赖，缺点是语义效果有限，适合 demo 或兜底。

第二种是 `sentence-transformers:<model>`。当前 `.env` 里配置的是：

```text
sentence-transformers:BAAI/bge-small-zh-v1.5
```

这是 BGE 中文 embedding 模型，常见输出维度是 512。项目代码不硬编码维度，而是直接使用模型返回的向量长度。

第三种是 OpenAI-compatible embeddings API。如果配置的是普通模型名，系统会调用兼容 `/embeddings` 的接口。这个时候输出维度由远程模型决定。

如果面试官问“为什么选 bge-small-zh-v1.5”，可以说：这个项目主要处理中文机厅信息和用户中文查询，BGE 中文模型效果比简单 hash 更好；small 版本资源占用较低，适合本地开发和轻量部署。

## 15. 向量数据库怎么构建

可以这样回答：

项目默认没有接 Milvus、Qdrant 或 pgvector，而是实现了本地向量索引。它支持两种 backend：memory 和 FAISS。

构建流程是：

```text
扫描 RAG_SOURCE_PATH
  -> 读取 md/txt/json/jsonl/pdf/docx/doc
  -> 生成文件 content_hash
  -> 文档切 chunk
  -> 每个 chunk 计算 chunk_hash
  -> 未变化 chunk 复用旧 embedding
  -> 新 chunk 调 embedding 模型
  -> 生成 _ChunkRecord
  -> 写入 memory 或 FAISS 索引
```

`memory` 模式下，所有 chunk record 都在进程内存里，查询时遍历计算 cosine similarity。它简单，适合小数据和开发调试。

`faiss` 模式下，会把所有 embedding 转成 float32 矩阵，先做 L2 normalize，然后用 `faiss.IndexFlatIP` 建索引。因为向量已经归一化，所以 inner product 基本等价于 cosine similarity。

FAISS 会落两个文件：

```text
data/runtime/rag_index.faiss
data/runtime/rag_index_meta.json
```

前者是向量索引，后者保存 chunk 文本、metadata、embedding model signature、chunk 配置和 source signature。这样服务重启后可以恢复索引，也能检查模型或切块参数变化后是否需要重建。

## 16. manifest 是什么

可以这样回答：

manifest 可以理解成“声明清单”。它不直接写业务逻辑，而是告诉系统有哪些东西、怎么加载、依赖什么、入口在哪里。

在这个项目里，面试时主要讲 builtin tool manifest：

```text
backend/app/agent/tools/builtin/tools_manifest.json
```

它里面主要有两块：

```text
services：声明共享服务怎么构造
tools：声明要加载哪些工具 JSON
```

比如 `services` 会声明 `db_query_tool`、`route_plan_tool`、`summary_tool` 这些服务的 factory 路径和依赖；`tools` 会列出 `schemas/db_query_tool.json`、`schemas/knowledge_search_tool.json` 等工具定义文件。

每个工具 JSON 又会声明：

- 工具名
- 工具描述
- 输入参数 JSON Schema
- executor 执行入口
- metadata

面试可以这样总结：

> manifest 是工具系统的声明式注册表。它把“工具有哪些、参数格式是什么、执行入口在哪里、依赖服务怎么装配”从代码里拆出来。后续新增工具时，不需要改一个中心化大 registry，只要新增 tool schema，并在 manifest 里挂上路径即可。

另外，前端还有 `manifest.webmanifest`，那是 PWA 用的，声明应用名、图标、启动路径和主题色，和 Agent 工具 manifest 不是一回事。

## 17. JSON Schema 有什么用

可以这样回答：

JSON Schema 是工具调用的参数契约。它规定模型调用某个工具时，参数 JSON 应该长什么样：有哪些字段、类型是什么、哪些必填、范围是多少、能不能多传字段。

比如 `db_query_tool` 会通过 schema 限制：

```text
page 必须是整数
page_size 有范围限制
sort_by 只能是指定枚举
origin_lng 必须在 -180 到 180
origin_lat 必须在 -90 到 90
additionalProperties=false，不允许乱传字段
```

它的作用主要有四个：

第一，约束模型输出。模型不是随便拼 JSON，而是必须按 schema 来。

第二，保护 executor。参数不合法时，在执行工具前就会被拦住，不会把脏数据传进业务逻辑。

第三，让工具更容易维护。新增工具时，把参数定义写在独立 JSON 文件里，不用把所有校验硬编码在 Python 里。

第四，方便模型理解工具怎么用。工具名、description 和 input_schema 会一起提供给模型，模型更容易生成正确 tool call。

面试版一句话：

> JSON Schema 把模型输出的自由 JSON 变成可校验的结构化输入，是 Agent 调工具时的参数契约。它既告诉模型怎么传参，也保护后端 executor 不被错误参数打穿。

## 18. builtin tool 是什么

可以这样回答：

builtin tool 是项目后端内置的业务工具，不是外部 MCP 工具，也不是模型参数里自带的能力。

Arcadegent 里的典型 builtin tools 有：

- `db_query_tool`：查询机厅数据。
- `knowledge_search_tool`：检索 RAG 知识库。
- `geo_resolve_tool`：做地点解析。
- `location_resolve_tool`：处理用户定位。
- `route_plan_tool`：规划路线。
- `summary_tool`：兼容性的 deterministic formatter。
- `invoke_worker`：让 main_agent 派发任务给 worker。

调用链路是：

```text
tools_manifest.json
  -> 加载 schemas/*.json
  -> ToolRegistry 注册工具
  -> LLM 产生 tool call
  -> JSON Schema 校验参数
  -> executor 执行业务逻辑
  -> 结果写回 working memory
```

面试可以这样说：

> builtin tool 是系统内置的业务能力。模型不会自己查数据库或规划路线，而是通过 tool call 调用这些工具。每个工具有 schema 约束参数，有 executor 负责真正执行，执行结果再回填到 working memory，供 Agent 继续推理和生成回答。

## 19. 增量索引是什么，为什么要做

可以这样回答：

增量索引就是知识库变化时，不把所有文档全部重新向量化，而是只处理新增、修改、删除的部分。

项目里的 RAG 索引流程大概是：

```text
扫描知识库文件
  -> 计算文件 content_hash
  -> 文档切 chunk
  -> 计算 chunk_hash
  -> 和旧索引对比
  -> 未变化 chunk 复用旧 embedding
  -> 新增或变化 chunk 才重新 embedding
  -> 删除文件对应 chunk 从索引移除
  -> 刷新 memory / FAISS 后端
```

为什么这么做：

第一，省时间。embedding 比普通文本处理慢，知识库只改一个文件时，没有必要全量重建。

第二，省成本。如果 embedding 走外部 API，重复向量化会产生额外成本。

第三，降低服务压力。全量重建会占 CPU、内存，FAISS 重建也有开销。

第四，让上传和删除更及时。用户上传一个文件后，只需要重建相关 chunk，系统可用性更好。

面试版总结：

> 增量索引的核心是文件级 `content_hash` 和 chunk 级 `chunk_hash`。文件没变就跳过，chunk 没变就复用旧 embedding，只有新增或变化的 chunk 才重新向量化。这样能减少索引构建时间、embedding 成本和服务压力。

## 20. RAG 处理 PDF 的逻辑

可以这样回答：

PDF 进入 RAG 后，项目用 `pypdf` 按页抽文本，再把每一页包装成统一的 Document，后续和 md、txt、docx 一样走切块、embedding 和索引流程。

流程是：

```text
PDF 文件
  -> PdfReader 读取
  -> 遍历每一页
  -> page.extract_text() 抽文本
  -> 空页跳过
  -> 每页生成 Document
  -> metadata 记录 title/source_uri/source_type
  -> LangChain splitter 切 chunk
  -> embedding
  -> 写入 memory 或 FAISS 索引
```

其中 `source_uri` 会带页码，例如：

```text
/path/to/handbook.pdf#page=3
```

这样命中后能知道答案来自 PDF 哪一页。

要说明一个边界：当前实现只支持文本型 PDF。它用的是 `page.extract_text()`，如果是扫描版图片 PDF，没有 OCR，大概率抽不到文本，会被当成空页跳过。

面试版总结：

> PDF 处理是按页抽取文本，每页转成统一 Document，并在 source_uri 里带上 page number。后续 PDF 不走特殊逻辑，而是复用统一的 RAG 流程：切块、chunk hash、embedding、memory/FAISS 建索引。当前没有 OCR，所以扫描版 PDF 需要后续接 OCR 才能检索。

## 21. 机厅检索条件是怎么实现的

可以这样回答：

机厅检索有两条入口：前端普通列表接口和 Agent 的 `db_query_tool`。底层都走同一个 `ArcadeRepository.list_shops()`，所以过滤规则是一套。

支持的条件主要有：

- `keyword`：通用关键词，比如 `广州 maimai`。
- `shop_name`：只按店名搜。
- `title_name`：按机种搜，比如 `maimai`、`CHUNITHM`。
- `province_code` / `city_code` / `county_code`：行政区 code 精确过滤。
- `province_name` / `city_name` / `county_name`：自然语言地区名过滤。
- `has_arcades`：是否必须有机种数据。
- `sort_by`：排序字段。
- `origin_lng` / `origin_lat`：附近搜索时的起点坐标。
- `page` / `page_size`：分页。

本地模式下，数据从 JSONL 加载到内存。每家店会构造一个 `_search_blob`，里面拼了店名、拼音、地址、交通、评论、省市区、机种名、版本和机种评论。

关键词检索是多 term 包含匹配：

```text
keyword = "广州 maimai"
terms = ["广州", "maimai"]
两个词都在 _search_blob 里才命中
```

店名搜索只查店名和拼音；机种搜索会做归一化，例如：

```text
舞萌 / maimai -> maimai
soundvoltex / sdvx -> sdvx
```

附近搜索会从 working memory 里取用户坐标，比如 `client_location` 或 `resolved_locations`，然后用 haversine 公式算直线距离，写入 `distance_m` 并按距离排序。

面试版总结：

> 机厅检索条件统一由 `ArcadeRepository.list_shops()` 实现。前端和 Agent tool 都传同一套参数。关键词通过 `_search_blob` 做多 term 包含匹配，地区支持 code 精确匹配和 name 归一化匹配，机种名会做别名归一化，附近搜索会读取用户坐标并计算直线距离排序。Supabase 模式下则把同样参数传给 `arcadegent_search_shops` RPC。

## 22. 异步会话怎么设计实现

可以这样回答：

异步会话的核心是把“发起任务”和“接收结果”拆开。前端调用 `POST /api/chat/sessions` 后，后端不等 Agent 跑完，而是先创建或占用 session，启动后台任务，然后立刻返回 `202 Accepted` 和 `session_id`。前端再用 SSE 订阅这个 session 的执行过程。

后端流程是：

```text
POST /api/chat/sessions
  -> Orchestrator.dispatch_chat()
  -> 补齐 session_id
  -> SessionStateStore.reserve_run()
  -> 设置 status/run_status = running
  -> asyncio.create_task(_run_chat_in_background)
  -> 立即返回 session_id
```

后台任务执行：

```text
ReactRuntime.run_chat()
  -> 写入用户 turn
  -> 准备 working memory
  -> 构造上下文
  -> 调 main_agent
  -> 执行工具和 worker
  -> 推送 SSE 事件
  -> 保存最终回复
  -> 标记 completed 或 failed
```

为了避免重复执行，项目用了 `idempotency_key`。同一个 session 同一个 idempotency_key 进来，会认为是同一次 run；如果 session 正在 running，但来了不同 key，就拒绝，避免两个 Agent 同时写同一个会话状态。

面试版总结：

> 异步会话是“HTTP 派发 + 后台任务 + SSE 订阅”。HTTP 只负责创建 run 和返回 session_id，Agent 在后台 task 里跑，过程事件写入 ReplayBuffer，前端通过 EventSource 实时消费。`run_status`、`active_sessions` 和 `idempotency_key` 用来做并发控制和幂等保护。

## 23. session_id 和事件 id 有什么区别

可以这样回答：

`session_id` 是会话 ID，表示是哪一场聊天；事件 id 是 SSE 事件流里的递增编号，表示这场聊天里第几条事件。

举个例子：

```text
session_id = s_abc123

id: 1
event: session.started

id: 2
event: subagent.changed

id: 3
event: tool.started

id: 4
event: assistant.token

id: 5
event: assistant.completed
```

这里 `s_abc123` 是这场对话的房间号，`1、2、3、4、5` 是这场对话里事件的顺序号。

如果前端收到 `id=3` 后断线，重连时会请求：

```text
GET /api/stream/s_abc123?last_event_id=3
```

后端就知道：还是 `s_abc123` 这场会话，但前端已经收到第 3 条事件了，只需要从第 4 条开始补发。

面试版总结：

> `session_id` 用来定位一场会话的状态、history 和 working memory；事件 id 是 SSE 流里的 offset，用来做事件排序和断线恢复。前端用 session_id 订阅哪场会话，用 last_event_id 告诉后端从哪里继续补发。

## 24. main_agent 和两个 worker 是怎么设计实现的

可以这样回答：

项目是 main_agent 加 worker 的多 Agent 设计。它们不是三个独立服务，而是同一个 ReAct Runtime 里不同的 subagent profile。

分工是：

- `main_agent`：负责理解用户意图、调度 worker、组织最终回答。
- `search_worker`：负责机厅搜索、附近推荐、知识检索 fallback。
- `navigation_worker`：负责目的地选择、地点解析和路线规划。

每个 subagent profile 包含：

```text
name
prompt_file
allowed_tools
skill_files
```

例如 search_worker 只给搜索相关工具，navigation_worker 才给路线规划工具。这样可以减少工具误用。

串联方式靠 `invoke_worker`：

```text
main_agent
  -> invoke_worker(worker=search_worker, task=...)
  -> ReactRuntime 创建 worker_state
  -> 切 active_subagent
  -> worker 调自己的工具
  -> worker 结果合并回父会话 working memory
  -> main_agent 基于结果生成最终回答
```

worker 执行期间还会通过 SSE 推：

```text
subagent.changed
worker.started
```

前端就能显示当前是“主控阶段”“检索执行”还是“导航执行”。

面试版总结：

> main_agent 是调度器，search_worker 和 navigation_worker 是执行角色。实现上，`SubAgentBuilder` 定义每个角色的 prompt、工具权限和 skill；main_agent 通过 `invoke_worker` 发任务，`ReactRuntime` 创建临时 worker_state 执行 worker，完成后把 shops、route、knowledge_hits 等结果合并回父 session 的 working memory。这样 prompt 更聚焦，工具权限更清晰，也方便通过 SSE 展示阶段变化。

## 25. trace_id 有什么用

可以这样回答：

trace_id 是链路追踪 ID，用来排查问题。它不是业务 ID，而是日志和执行链路里的线索编号。

HTTP 层每个请求都会有：

```text
X-Request-Trace-Id
```

如果前端传了，后端沿用；如果没传，后端生成一个 `srv_xxx`，写进响应头和 access log。这样用户说“刚才那个请求失败了”时，可以用 trace_id 去日志里查路径、状态码和耗时。

Agent 工具链路里也会记录 trace 信息，比如：

```text
trace_id
tool_trace_id
call_id
```

它们用来串起一次 Agent 执行里的多个 tool call。比如一次附近搜索可能会经历：

```text
invoke_worker
location_resolve_tool
db_query_tool
knowledge_search_tool
```

trace 信息可以帮助定位是哪一步失败、参数是什么、是否 fallback、耗时多久。

几个 ID 的区别可以这样讲：

```text
session_id：哪场聊天
trace_id：这次请求或执行链路怎么走的
event_id：SSE 里的第几条事件
call_id：某一次具体工具调用
```

面试版总结：

> trace_id 主要服务于可观测性和问题排查。HTTP 请求有 `X-Request-Trace-Id`，Agent 工具调用也有 trace 信息，可以把一次用户请求下的 session、工具调用、日志、错误和耗时串起来。线上出现“搜索没结果”或“路线规划失败”时，就能沿着 trace_id 找到问题点。

## 26. 历史会话管理怎么设计实现

可以这样回答：

历史会话管理是后端 `SessionStateStore` 和前端 localStorage 配合实现的。后端按 `session_id` 保存完整会话状态，前端保存当前客户端 ID、当前选中的 session 和 SSE offset。

后端每个 session 保存的是 `AgentSessionState`，包括：

```text
session_id
client_id
turn_index
active_subagent
intent
status
run_status
idempotency_key
last_stream_offset
last_error
turns
working_memory
created_at
updated_at
```

其中：

- `turns` 保存用户、助手和工具记录。
- `working_memory` 保存 shops、route、knowledge_hits 等结构化状态。
- `last_stream_offset` 保存最后推到哪条 SSE 事件。
- `client_id` 用来区分不同浏览器客户端的会话归属。

持久化上，后端内存里用 dict 管理：

```text
_states[session_id] = AgentSessionState
```

同时会落盘成每个 session 一个 JSON 文件：

```text
data/runtime/chat_sessions/
  s_xxx.json
  s_yyy.json
```

写文件时会用临时文件 replace，并配合 `.lock` 文件和 `fcntl.flock` 做并发保护。

对外接口有：

```text
GET /api/chat/sessions
GET /api/chat/sessions/{session_id}
DELETE /api/chat/sessions/{session_id}
```

删除时如果 session 正在 running，会返回 409，不允许删正在执行的会话。

前端 localStorage 保存：

```text
arcadegent.chat.clientId.v1
arcadegent.chat.activeSessionId.v1
arcadegent.chat.streamOffsets.v1
```

刷新页面后，前端会拉会话列表，恢复 active session；如果会话还在 running，就根据 stream offset 重新订阅 SSE。

面试版总结：

> 历史会话不是只存聊天文本，而是存完整的 session state。后端用 `SessionStateStore` 保存 turns、working memory、状态和 SSE offset，并落盘成 session JSON；前端用 localStorage 保存 client_id、active_session_id 和 stream offsets。这样可以支持会话列表、详情恢复、删除历史、刷新后继续当前会话，以及 running 会话的 SSE 断点续接。

## 27. 最后一版项目总结

可以这样收尾：

Arcadegent 的核心是一个业务型 Agent 链路。前端用 React 展示聊天、地图和流式状态；后端用 FastAPI 提供 API 和 SSE；Agent 层用自研 ReAct Runtime 串起 main_agent、search_worker、navigation_worker 和工具注册表。上下文不是只靠聊天历史，而是用 turn history、working memory 和 context payload 一起管理。RAG 这块用了 LangChain 做文档切分，用 sentence-transformers 或外部 embedding 做向量化，用 memory 或 FAISS 做本地索引，并支持向量召回、BM25 召回、加权融合和可选 reranker。

同时我也会诚实说明边界：项目没有使用 LangGraph，没有默认接外部向量数据库，也没有自动上下文压缩和自动 skill 沉淀闭环。这些反而是后续可以继续工程化的方向。
