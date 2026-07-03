# Arcadegent 面试题库与深度追问

这份文档面向基于 Arcadegent 项目做项目面试、答辩或技术复盘的场景。

目标不是只给一个“项目介绍”，而是把高频问题、考察知识点、标准回答、深度追问和可继续展开的答案整理成一份可复习的题库。

说明：

- 严格意义上不可能穷尽“所有问题”，但这份题库已经覆盖了基于当前仓库实现最可能被问到的主线问题和延展追问。
- 回答以“工程实现 + 设计取舍 + 可扩展性”三层展开，既适合一面，也适合二面和深挖。
- 如果你时间很紧，优先背“30 秒项目介绍”和每节里的“参考回答”。

## 1. 30 秒项目介绍

### 可能问题

请你用 30 秒介绍一下这个项目。

### 具体知识点

- 全栈架构
- 前后端分离
- Agent 编排
- SSE 实时流
- 地图与地理能力
- 数据源抽象

### 参考回答

Arcadegent 是一个面向音游机厅检索、Agent 问答和路线建议的全栈应用。前端使用 React + TypeScript + Vite + Zustand，负责聊天界面、机厅浏览器和高德地图渲染；后端使用 FastAPI，内部做了 ReAct 风格的 Agent 运行时、工具注册表、会话状态持久化和 SSE 流式推送。数据层既支持本地 JSONL 读模型，也支持 Supabase RPC 读模型，适合本地开发和线上部署两种模式。项目的核心不是单纯做聊天，而是把搜索、地理解析、路线规划和前端地图展示串成一个完整闭环。

### 深度追问

这个项目和普通“聊天机器人”项目最大的区别是什么？

### 深度追问回答

最大的区别是它不是“只返回一段文本”的聊天机器人，而是一个带结构化工具执行链路的业务型 Agent。它会先识别意图，再调用搜索、地理解析、路线规划等工具，把结构化结果写入 working memory，最后输出文本回答，同时通过 SSE 把过程事件和地图 artifacts 推给前端。也就是说，它的核心价值在于“推理 + 工具 + UI 展示”的闭环，而不是模型单点输出。

### 源码定位

- `README.md`
- `backend/app/main.py`
- `backend/app/core/container.py`
- `backend/app/agent/runtime/react_runtime.py`
- `apps/web/src/hooks/useChatSessionController.ts`

---

## 2. 为什么采用前后端分离

### 可能问题

为什么这个项目采用前后端分离，而不是直接用服务端模板渲染？

### 具体知识点

- SPA
- API-first
- 流式响应
- 地图 SDK 集成
- 前后端职责分离

### 参考回答

这个项目需要同时处理聊天流式输出、地图渲染、浏览器定位、会话恢复和机厅浏览器筛选，这些都更适合放在前端单页应用里完成。后端主要负责数据查询、Agent 编排、工具执行和流式事件输出，前端负责消费 API 与 SSE 事件并做状态管理。这样做的好处是职责边界清晰，前端可以独立优化交互体验，后端可以专注在业务编排和可扩展性上。

### 深度追问

那为什么不做成 Next.js 这类一体化方案？

### 深度追问回答

如果项目重点是内容渲染或 SEO，一体化方案会更合适；但 Arcadegent 的核心是强交互场景，尤其是 EventSource 流、地图 SDK、会话状态恢复和浏览器定位，这些更像典型 SPA。当前方案把前端部署成静态站点，把后端做成独立 API 服务，部署和扩缩容也更简单。另外后端还承担 Agent 运行时，和页面渲染本身没有强绑定，所以拆开更自然。

### 源码定位

- `apps/web/package.json`
- `apps/web/vite.config.ts`
- `backend/app/api/http/chat.py`

---

## 3. 整体架构怎么分层

### 可能问题

你怎么描述这个项目的整体架构？

### 具体知识点

- 分层架构
- 组合根
- API 层
- 应用服务层
- 基础设施层
- 前端状态层

### 参考回答

后端大致分成五层。第一层是 HTTP 和 SSE API 层，负责暴露 `/api/chat`、`/api/chat/sessions`、`/api/stream/{session_id}` 这类接口。第二层是组合和生命周期层，由 `create_app` 和 `build_container` 统一装配依赖。第三层是 Agent 运行时层，核心是 `ReactRuntime` 和 `Orchestrator`，负责意图识别、上下文构建、工具调用和回复生成。第四层是工具与服务层，包括内建工具、MCP 工具、高德逆地理、机厅地理补全等能力。第五层是数据基础设施层，抽象成 `ArcadeRepository`，底层可切到 JSONL 或 Supabase。前端则分成视图组件、状态管理、API 客户端和聊天控制器四层。

### 深度追问

为什么说 `build_container` 是组合根？

### 深度追问回答

因为所有长生命周期依赖都在这里集中构建，包括仓储、会话存储、replay buffer、地图服务、工具注册表、LLM provider adapter、ReactRuntime 和 Orchestrator。它的作用类似依赖注入容器的 composition root，让依赖关系只在一个地方装配，避免在业务代码里到处 new 对象。这样做更利于测试替换、环境切换和后续扩展。

### 源码定位

- `backend/app/main.py`
- `backend/app/core/container.py`
- `apps/web/src/App.tsx`
- `apps/web/src/stores/appStore.ts`

---

## 4. 为什么后端选 FastAPI

### 可能问题

为什么后端选择 FastAPI？

### 具体知识点

- ASGI
- 异步 IO
- Pydantic
- OpenAPI
- 生命周期管理

### 参考回答

FastAPI 比较适合这个项目的原因有三个。第一，它天然适合异步接口，项目里需要对接 LLM、地图服务和 Supabase RPC，异步模型更友好。第二，它和 Pydantic 结合紧密，请求响应模型和参数校验都很方便。第三，它对 SSE、依赖注入、生命周期和 OpenAPI 文档支持都比较自然，适合快速搭建一套结构清晰的 API 服务。

### 深度追问

FastAPI 的依赖注入在这个项目里体现在哪里？

### 深度追问回答

体现得最明显的是 `get_container` 注入 `AppContainer`。API 层不自己构造仓储、运行时和服务，而是通过依赖注入从 `app.state` 获取已经装配好的容器。这样 API 层就是薄控制器，只做参数接收、错误转换和 DTO 返回，业务依赖不会散落到路由函数里。

### 源码定位

- `backend/app/main.py`
- `backend/app/api/deps.py`
- `backend/app/api/http/chat.py`

---

## 5. 聊天为什么用了异步派发加 SSE

### 可能问题

为什么没有只做同步接口返回，而是用了 `POST /chat/sessions` 加 SSE？

### 具体知识点

- 异步任务派发
- SSE
- 长连接
- 流式 UI
- 事件驱动前端

### 参考回答

同步接口适合一次请求一次响应，但这个项目的 Agent 过程会经历会话启动、子 Agent 切换、工具调用、路线生成、token 流式返回等多个阶段。如果全部等后端跑完再一次性返回，用户会觉得系统很慢，也看不到中间过程。所以项目采用“先派发会话，再用 SSE 订阅事件流”的模式，让前端可以逐步展示进度、路线和最终回复，这更符合 Agent 产品的体验。

### 深度追问

为什么选 SSE 而不是 WebSocket？

### 深度追问回答

这里的通信模型本质上是后端单向推送，前端只需要订阅事件，不需要高频双向交互，因此 SSE 已经足够，而且实现和接入成本更低。浏览器原生支持 `EventSource`，自动重连、事件名和 `Last-Event-ID` 机制也比较适合会话回放。WebSocket 更适合协同编辑、多人聊天室或复杂双工场景，但这里会增加实现复杂度和运维成本。

### 源码定位

- `backend/app/api/http/chat.py`
- `backend/app/api/stream/sse.py`
- `apps/web/src/hooks/useChatSessionController.ts`

---

## 6. SSE 断线重连和事件回放是怎么做的

### 可能问题

如果前端断线了，聊天过程怎么恢复？

### 具体知识点

- SSE `Last-Event-ID`
- 事件回放
- replay buffer
- 幂等恢复

### 参考回答

后端为每个 session 维护了一个 replay buffer，SSE 事件带递增 id。前端断开后重新连接时，可以带上 `Last-Event-ID` 或查询参数 `last_event_id`，后端会从这个 id 之后继续补发事件。如果会话已经结束，SSE 会自然收口；如果还在运行，会继续推送后续事件。这样用户刷新页面或网络抖动后，仍然能恢复到接近实时的状态。

### 深度追问

replay buffer 为什么还需要和 session store 配合？

### 深度追问回答

replay buffer 解决的是“事件流回放”，适合恢复过程；session store 解决的是“最终状态快照”，适合恢复结果。比如前端如果错过了一部分 token 事件，最终仍然可以通过 `GET /api/chat/sessions/{session_id}` 拿到完整 turns、shops、route 和 reply。一个偏过程，一个偏状态，两者组合起来恢复体验更稳。

### 源码定位

- `backend/app/agent/events/replay_buffer.py`
- `backend/app/api/stream/sse.py`
- `backend/app/agent/runtime/session_state.py`

---

## 7. 为什么要有 Orchestrator

### 可能问题

既然已经有 `ReactRuntime` 了，为什么还要再包一层 `Orchestrator`？

### 具体知识点

- 外观模式
- 后台任务调度
- 会话并发控制
- 同步与异步执行解耦

### 参考回答

`ReactRuntime` 更像真正的业务执行引擎，负责跑完整个 Agent 会话；`Orchestrator` 是一层外观和调度器，负责把“同步执行”和“后台派发执行”两种入口统一起来，同时做 session 级别的并发控制。这样 API 层只需要依赖 Orchestrator，不需要直接关心后台任务创建、运行中 session 锁和清理逻辑。

### 深度追问

这里的并发控制具体解决了什么问题？

### 深度追问回答

它主要防止同一个 session 被重复提交，导致 working memory、turns 和 SSE 事件互相污染。`Orchestrator` 用 `_active_sessions` 集合和线程锁来确保同一时间一个 session 只能有一个运行任务，如果重复派发就返回 409。这个控制虽然简单，但对会话一致性很关键。

### 源码定位

- `backend/app/agent/runtime/orchestrator.py`

---

## 8. Agent 运行时为什么采用 ReAct 风格

### 可能问题

你们的 Agent 运行时为什么采用 ReAct 风格，而不是纯 prompt chaining？

### 具体知识点

- ReAct
- 工具调用
- 工作记忆
- 循环控制
- 多步骤推理

### 参考回答

这个项目的回复不是纯生成型任务，而是明显需要“先判断、再查、再总结”的链路，比如搜索附近机厅、补地理坐标、规划路线、再组织答案。ReAct 风格的优势是把推理和行动交替组织起来，让模型可以在每一步基于 observation 决定下一步是否继续调用工具或结束回答。这样比一条大 prompt 更适合业务型 Agent，也更容易加事件观测和中间状态控制。

### 深度追问

如果模型陷入死循环怎么办？

### 深度追问回答

项目里用 `LoopGuard` 控制最大步数，`ReactRuntime` 也会把 `max_steps` 作为硬边界。一旦模型没有在限定步数内收敛，就会走 fallback 路径，避免无限工具调用或超长响应。这是 ReAct 类系统里很常见的保护措施，因为真实模型并不保证每次都稳定收敛。

### 源码定位

- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/runtime/loop_guard.py`

---

## 9. working memory 是怎么设计的

### 可能问题

working memory 在这个项目里承担什么作用？

### 具体知识点

- 会话状态
- 中间工件
- artifact
- 多轮对话记忆
- 状态归一化

### 参考回答

working memory 是整个 Agent 会话的结构化中间态，里面会记录 `last_request`、`keyword`、`shops`、`shop`、`route`、`destination`、`client_location`、`reply` 等信息。它的作用不是直接给用户看，而是让模型、工具执行和最终 API 输出共享同一份中间工件。项目里还用 `ensure_working_memory_shape` 保证 memory 至少包含 `artifacts` 和 `worker_runs` 这些关键结构，方便后续演进。

### 深度追问

为什么不直接把所有状态都平铺在 session 对象上？

### 深度追问回答

因为平铺会让 session 顶层字段越来越多，后续 schema 演进很难控。把可变的中间工件收拢到 working memory 中，本质上是在做“可演化状态容器”。这样新增一个 route、view_payload 或某个工具观测值时，不需要频繁改 session 顶层模型，也更适合和 context builder 对接。

### 源码定位

- `backend/app/agent/runtime/session_state.py`
- `backend/app/agent/runtime/react_runtime.py`

---

## 10. ContextBuilder 的价值是什么

### 可能问题

为什么要单独做 `ContextBuilder`，而不是在运行时里直接拼 prompt？

### 具体知识点

- prompt engineering 工程化
- 上下文分层
- 目录式上下文
- LLM 可读性优化

### 参考回答

`ContextBuilder` 把“如何组织上下文”从运行时里拆了出来，避免 prompt 拼装逻辑散落在执行流程中。它的目标不是写死模板答案，而是把 session state、请求、技能片段和历史 turn 组织成适合 LLM 消费的结构化上下文。文档里强调了 `directory + detail block` 的思路，本质上是在做上下文信息架构优化，减少模型注意力被重字段干扰。

### 深度追问

为什么文档里强调不要把 agent 做成 template agent？

### 深度追问回答

因为模板 agent 的本质是把回答写死，一旦场景变复杂，代码里会堆满 if-else，最后不是模型在推理，而是工程代码在硬编码回答路径。这个项目想保留 LLM 对结构化信息的阅读和组织能力，因此工具只做确定性工作，context 和 skill 负责“怎么读”，最终回答仍由 agent 来生成，这样扩展性更强。

### 源码定位

- `backend/app/agent/context/context_builder.py`
- `backend/app/agent/context/prompts/`
- `docs/dev-details/agent-context-payload-design.md`

---

## 11. 工具注册表为什么要做成 provider 模式

### 可能问题

你们的工具系统为什么不是简单的一个字典映射，而是 provider 化的注册表？

### 具体知识点

- provider pattern
- 工具发现
- JSON Schema 校验
- 权限控制
- 动态扩展

### 参考回答

因为项目既有内建工具，也有 MCP 工具，如果直接做成单一字典映射，很快就会把发现、校验、执行、权限和健康检查逻辑揉在一起。现在的 `ToolRegistry` 只负责聚合 provider、做权限检查、按 descriptor 校验参数并把执行路由到对应 provider。内建工具和 MCP 工具都通过统一接口接入，这样后续加新的工具来源时不需要推翻整个架构。

### 深度追问

JSON Schema 校验在这里的意义是什么？

### 深度追问回答

工具调用是模型驱动的，最容易出问题的就是参数格式不稳定。使用 JSON Schema 校验可以把“模型生成的参数”和“工具真正接受的参数”之间建立显式契约，及早发现字段缺失、类型错误和不合法枚举。这样能把很多运行时错误前移到调用前，并且校验结果也更容易回传给模型或日志。

### 源码定位

- `backend/app/agent/tools/registry.py`
- `backend/app/agent/tools/base.py`
- `backend/app/agent/tools/schemas.py`
- `docs/dev-details/dynamic-tool-registry-implementation.md`

---

## 12. 内建工具和 MCP 工具分别解决什么问题

### 可能问题

为什么同时保留 builtin tools 和 MCP tools？

### 具体知识点

- 内建工具
- 外部工具协议
- MCP
- 本地能力与远程能力分层

### 参考回答

内建工具适合承载本项目强绑定的能力，比如本地数据库查询、路线规划封装、地理解析和确定性格式化；MCP 工具更适合承载可插拔的外部能力，比如第三方地图 endpoint。这样做的好处是核心能力仍掌握在项目内部，可控、可测试；同时又保留通过 MCP 接外部生态的扩展空间，不会把系统绑死在某一个外部服务实现上。

### 深度追问

如果 MCP 服务挂了，系统会完全不可用吗？

### 深度追问回答

不一定。项目的搜索和基础会话流不依赖 MCP 本身就能工作，MCP 更多是扩展地图或工具能力。健康检查里也会暴露 MCP discovery 状态和每个 server 的可用工具数。理想设计是让缺失 MCP 时相关能力降级，而不是整站不可用，这也是为什么工具系统被拆成 provider 并支持 health 信息。

### 源码定位

- `backend/app/agent/tools/builtin/`
- `backend/app/agent/tools/mcp/`
- `backend/app/agent/tools/mcp_gateway.py`

---

## 13. LLM Provider 为什么做成 OpenAI-compatible 抽象

### 可能问题

为什么不是直接把 OpenAI SDK 写死？

### 具体知识点

- provider adapter
- OpenAI-compatible API
- 模型替换成本
- 平台解耦

### 参考回答

业务层真正依赖的是“能不能完成聊天和工具调用”，而不是某个厂商 SDK 本身。把 LLM 接口抽象成 OpenAI-compatible provider 后，项目就能比较低成本地切换到支持同类协议的不同模型服务，比如 OpenAI、DeepSeek 或其他兼容实现。这样在成本、延迟、模型能力和可用性之间有更大的选择空间。

### 深度追问

这种抽象会不会掩盖不同模型的能力差异？

### 深度追问回答

会，所以抽象不能只停留在“统一一个 URL”。项目里还有 subagent profile、tool policy、provider profile 这类配置，本质上是把“统一接口”和“差异化能力配置”分开处理。也就是说，调用入口可以统一，但模型特性、温度、工具策略和上下文约束仍然可以按 profile 区分。

### 源码定位

- `backend/app/agent/llm/provider_adapter.py`
- `backend/app/agent/llm/llm_config.py`
- `backend/app/infra/llm/openai_compatible_client.py`

---

## 14. 数据层为什么要支持 JSONL 和 Supabase 两套实现

### 可能问题

为什么仓储层做了本地 JSONL 和 Supabase RPC 两种实现？

### 具体知识点

- repository pattern
- 数据源抽象
- 本地开发与线上部署
- 读模型

### 参考回答

这个项目的数据需求本质上是“读多写少”的机厅检索，因此非常适合先做读模型抽象。JSONL 模式适合本地开发和轻量部署，不依赖数据库就能跑起来；Supabase 模式适合线上共享数据源和更标准的服务化部署。通过 `ArcadeRepository` 抽象，两种实现对上层 API 和 Agent 基本透明，降低了环境切换成本。

### 深度追问

为什么 Supabase 这里是走 RPC，而不是前端常见的表查询？

### 深度追问回答

这里更像后端服务读模型，而不是浏览器直接查表。走 RPC 有几个好处：可以把筛选、排序、分页和兼容逻辑收在数据库侧；接口契约更稳定；也更容易控制暴露面。另外一些组合查询和排序逻辑如果放在浏览器端拼 PostgREST 语句，会让前端和数据库结构耦合更深。

### 源码定位

- `backend/app/core/container.py`
- `backend/app/infra/db/repository.py`
- `backend/app/infra/db/local_store.py`
- `backend/app/infra/db/supabase_repository.py`

---

## 15. 本地 JSONL 方案的优缺点是什么

### 可能问题

本地 JSONL 读模型为什么可行？它的优缺点是什么？

### 具体知识点

- 读模型
- 内存索引
- 搜索 blob
- 排序和筛选
- 轻量部署

### 参考回答

JSONL 模式适合数据相对可控、更新频率不高、以读取为主的场景。项目启动时把 JSONL 读入内存，并构建用于关键字检索的 search blob，这样后续搜索和地区筛选都可以在内存中快速完成。优点是部署简单、依赖少、调试方便；缺点是数据量上来之后启动时间、内存占用和多实例一致性都会变差，也不适合高并发写入。

### 深度追问

如果数据量扩大十倍，你会怎么改？

### 深度追问回答

第一步会把 JSONL 从运行时主读源升级成离线导入格式，把线上读流量切到数据库或搜索引擎。第二步会把关键词检索、距离排序和地区过滤下沉到数据库索引或搜索服务中。第三步会把 geo cache、会话状态和事件缓存都外部化，避免单实例内存成为瓶颈。也就是说，JSONL 方案更适合早期和单机阶段，不适合作为长期主存储。

### 源码定位

- `backend/app/infra/db/local_store.py`

---

## 16. 距离排序和附近搜索是怎么做的

### 可能问题

附近搜索和距离排序在后端是怎么实现的？

### 具体知识点

- Haversine
- 坐标系统
- 排序稳定性
- 地理筛选

### 参考回答

本地仓储里会先取出门店候选，再根据原点经纬度计算距离。距离算法用的是 Haversine，适合中短距离球面距离估算。排序时还考虑了坐标系统优先级和无坐标数据的回退逻辑，如果门店没有可用坐标，会放到后面，避免影响已定位门店的排序结果。

### 深度追问

为什么不能简单用经纬度差值排序？

### 深度追问回答

因为经纬度不是等距坐标系，尤其不同纬度上经度差对应的实际距离不一样。直接用差值只适合非常粗略的近似，而且误差不可控。Haversine 至少考虑了地球曲率，虽然不是导航级精度，但对“附近排序”这种场景已经足够实用。

### 源码定位

- `backend/app/infra/db/local_store.py`

---

## 17. 地图坐标为什么要区分 WGS84 和 GCJ-02

### 可能问题

为什么地图部分要专门处理坐标系转换？

### 具体知识点

- WGS84
- GCJ-02
- 浏览器定位
- 中国地图偏移
- 坐标转换

### 参考回答

浏览器定位和很多通用地理接口默认给的是 WGS84，而高德地图展示体系使用的是 GCJ-02。如果不做区分，地图 marker 和路线会出现明显偏移。所以项目里把 `client_location` 保留为浏览器定位语义，再在前端渲染地图或生成高德 URI 前转换为 GCJ-02，这样既保留原始语义，也保证展示正确。

### 深度追问

为什么不在后端统一全转成 GCJ-02？

### 深度追问回答

因为 `client_location` 的来源是浏览器定位，保留原始语义更利于调试、回放和后续切换地图服务。真正需要 GCJ-02 的是“和高德地图绑定的展示层”。把转换放在靠近展示的地方，职责更清晰，也避免不同下游都默认使用同一种坐标而丢掉原始来源信息。

### 源码定位

- `apps/web/src/lib/amapCoords.ts`
- `docs/dev-details/agent-map-artifacts-rendering.md`
- `docs/dev-details/browser-location-reverse-geocoding.md`

---

## 18. 为什么地图展示不让模型直接返回 HTML

### 可能问题

为什么地图展示采用 structured artifacts，而不是让模型直接输出 HTML 或组件描述？

### 具体知识点

- 结构化输出
- 表现层安全
- UI 可控性
- 契约式前后端协作

### 参考回答

让模型直接输出 HTML 或组件树看起来灵活，但可控性和安全性都很差。这个项目采用结构化 artifacts 契约，让模型或工具只决定“数据是什么”，前端固定组件决定“怎么展示”。这样能保证地图、路线卡片和按钮行为稳定，也避免模型输出不合法结构、不可控样式甚至潜在注入风险。

### 深度追问

那文本为什么还能用 Markdown？

### 深度追问回答

文本天然适合让模型自由组织，而地图是强交互结构化视图，二者边界不一样。项目里 Assistant 正文可以走 Markdown，但地图相关内容必须走 `shops`、`route`、`destination`、`view_payload` 这些结构化字段，再由 React 组件渲染。这个边界能同时兼顾自然语言表达能力和 UI 稳定性。

### 源码定位

- `docs/dev-details/agent-map-artifacts-rendering.md`
- `apps/web/src/components/ChatPanel.tsx`
- `apps/web/src/components/map/AgentMapCard.tsx`

---

## 19. 前端为什么选 Zustand

### 可能问题

为什么前端状态管理选 Zustand，而不是 Redux 或 Context？

### 具体知识点

- 轻量状态管理
- 全局状态
- 流式 UI 状态
- store 分层

### 参考回答

这个项目的全局状态主要集中在会话列表、当前 session、turns、stream 状态、子 Agent 状态和地图 artifacts 上，规模中等但更新频率高。Zustand 足够轻量，不需要引入 Redux 那套 action/reducer 样板代码，同时又比纯 Context 更适合高频更新和模块化拆分。项目里还把聊天主状态和机厅浏览器状态分成两个 store，边界相对清晰。

### 深度追问

这种 store 设计的潜在问题是什么？

### 深度追问回答

潜在问题是随着业务增长，store 可能变成“大而全”的共享状态仓库，导致耦合上升。解决思路通常是继续按领域拆 store，或者把复杂业务逻辑抽到 controller/hook 层，保证 store 只承载状态和简单 setter。当前项目其实已经朝这个方向走了，因为 `useChatSessionController` 承担了较多流程编排。

### 源码定位

- `apps/web/src/stores/appStore.ts`
- `apps/web/src/stores/arcadeBrowserStore.ts`

---

## 20. 聊天控制器层解决了什么问题

### 可能问题

前端为什么要单独做 `useChatSessionController`？

### 具体知识点

- 控制器模式
- 视图与副作用分离
- SSE 消费
- 会话恢复

### 参考回答

聊天流程涉及发送请求、创建 session、连接 EventSource、消费不同事件、刷新会话详情、恢复本地 active session id 和同步地图 artifacts，如果这些逻辑都堆在组件里，会让视图层非常难维护。`useChatSessionController` 把这些副作用和流程控制抽离出去，让组件主要关注展示，控制器负责状态编排，这是比较典型的前端 controller/hook 分层。

### 深度追问

`assistant.token` 和 `assistant.completed` 为什么要分开处理？

### 深度追问回答

`assistant.token` 主要服务流式体验，让用户边看边等；`assistant.completed` 则是最终收口信号，表示这轮回复结束，前端可以把 session 状态切成 completed，并重新拉取会话详情获得稳定快照。也就是说，一个偏体验，一个偏一致性，两者缺一不可。

### 源码定位

- `apps/web/src/hooks/useChatSessionController.ts`
- `apps/web/src/hooks/useStreamReply.ts`

---

## 21. 会话状态为什么要落盘

### 可能问题

为什么 `SessionStateStore` 不是纯内存，而是支持写入本地 JSON？

### 具体知识点

- 状态持久化
- 故障恢复
- 单实例容错
- 快照存储

### 参考回答

纯内存虽然简单，但服务重启后会话就完全丢失。项目把 session snapshots 落到本地 JSON，至少可以支持历史会话恢复、开发调试和轻量级故障恢复。这种方案不是高可用设计，但对于单机部署和早期项目很实用，成本也低。

### 深度追问

这种落盘方案的局限是什么？

### 深度追问回答

局限主要有三点。第一，它适合单实例，不适合多副本共享。第二，保存时会重写整个快照文件，数据量大了后 IO 成本会上升。第三，它不是事务性数据库，无法很好处理复杂并发和跨进程协调。所以如果项目要上更高规模，session store 应该迁移到 Redis 或数据库。

### 源码定位

- `backend/app/agent/runtime/session_state.py`

---

## 22. 这个项目是怎么保证 API 和会话安全边界的

### 可能问题

项目里没有完整登录系统时，怎么避免用户串看会话？

### 具体知识点

- client scope
- 轻量访问控制
- session ownership

### 参考回答

当前项目使用的是轻量 client scope 模型。前端会生成或读取本地 `client_id`，后端在 session state 上记录 `client_id`，后续查询、删除和 SSE 订阅都会按 `client_id` 做可见性过滤。如果不是该 client 的 session，接口会返回 not found。这不等于真正的账号体系，但在无登录场景下已经提供了一层基本隔离。

### 深度追问

这种方案在安全上还有什么不足？

### 深度追问回答

它更像“弱隔离”而不是真认证，因为 `client_id` 本质上仍由前端持有。如果有更高安全要求，就需要引入用户登录、签名 token 或服务端会话鉴权，把 session ownership 绑定到可信身份，而不是浏览器本地标识。当前方案适合轻量应用和低风险场景。

### 源码定位

- `backend/app/agent/runtime/session_state.py`
- `backend/app/api/http/chat.py`
- `apps/web/src/lib/chatSessionStorage.ts`

---

## 23. 测试策略是怎么设计的

### 可能问题

这个项目的测试怎么分层？

### 具体知识点

- 单元测试
- 集成测试
- 端到端测试
- mock 外部依赖

### 参考回答

测试分成三层。第一层是后端单元测试，验证地理补全等相对独立逻辑。第二层是 API 集成测试，覆盖 FastAPI 接口和主要业务链路。第三层是前端 Playwright 端到端测试，覆盖真实浏览器交互。因为项目依赖地图服务和 LLM，所以合理的测试策略不是全量打真服务，而是通过 mock MCP server、假数据和稳定的 API fixture 来保证可重复性。

### 深度追问

Agent 项目测试最难的地方是什么？

### 深度追问回答

最难的是结果天然带非确定性，尤其一旦引入真实 LLM，输出很难严格断言。所以测试重点通常会从“文本完全一致”转到“协议、状态迁移、工具调用、结构化输出和错误处理是否符合预期”。也就是说，应该优先测确定性边界，而不是过度依赖模型逐字输出。

### 源码定位

- `backend/app/tests/`
- `apps/web/playwright.config.ts`

---

## 24. 部署方案为什么用 Docker Compose

### 可能问题

这个项目的部署方式有什么考虑？

### 具体知识点

- 容器化
- 多服务编排
- 静态站点部署
- 环境隔离

### 参考回答

当前仓库的部署结构是比较典型的双服务模式：后端是 Python + Uvicorn，前端是构建后的静态资源，由 Nginx 托管。Docker Compose 可以把这两部分以及环境变量、网络和启动顺序编排起来，非常适合本地联调和中小规模部署。这个方案实现成本低，也方便后续拆到更正式的容器平台。

### 深度追问

如果要上生产并做多实例扩展，你最先改什么？

### 深度追问回答

我会先把 session store 和 replay buffer 外部化，因为这是当前最明显的单实例状态瓶颈。然后再处理数据层、日志、监控和反向代理配置，最后才是前后端服务本身的副本扩展。否则服务副本数量加了，但会话和流式状态不共享，用户体验反而会变差。

### 源码定位

- `docker-compose.yml`
- `backend/Dockerfile`
- `apps/web/Dockerfile`
- `apps/web/nginx.conf`

---

## 25. 你认为这个项目当前最大的技术风险是什么

### 可能问题

如果你来做技术复盘，你认为这个项目最大的风险点在哪里？

### 具体知识点

- 单实例状态
- 可扩展性
- 外部依赖不稳定性
- Agent 非确定性

### 参考回答

我认为最大的风险有三个。第一是会话状态和 replay buffer 仍然偏单实例，横向扩展成本高。第二是项目依赖地图服务和 LLM，两类外部服务都会带来延迟和不稳定性。第三是 Agent 本身有非确定性，测试和故障排查都比传统 CRUD 系统更复杂。所以这个项目当前更像是产品能力已经打通，但平台化和高可用能力仍在早期阶段。

### 深度追问

如果给你两周时间做一次技术增强，你会优先做哪三件事？

### 深度追问回答

第一，把 session store 和事件缓存迁到 Redis，解决单实例问题。第二，补齐可观测性，包括工具调用耗时、LLM 耗时、SSE 会话指标和错误分类。第三，完善 Agent 回归测试，重点覆盖意图识别、工具参数校验、路线 artifacts 和失败回退。这三件事分别对应可扩展性、可运维性和可回归性。

### 源码定位

- `backend/app/agent/runtime/session_state.py`
- `backend/app/agent/events/replay_buffer.py`
- `backend/app/agent/runtime/react_runtime.py`

---

## 26. 如果让你重构一次，你会怎么做

### 可能问题

你会如何继续演进这个项目？

### 具体知识点

- 架构演进
- 可扩展性
- 模块边界
- 平台化

### 参考回答

我会沿三个方向继续演进。第一，把运行时状态外部化，让系统从单机 Agent 应用升级成可横向扩展的服务。第二，把工具能力进一步模块化，形成更稳定的 builtin tool bundle 和 MCP 扩展机制。第三，加强前端领域拆分，把聊天、地图和机厅浏览器做成更稳定的领域模块。整体目标是从“功能打通”走向“平台可维护”。

### 深度追问

重构时最需要避免的坑是什么？

### 深度追问回答

最需要避免的是为了“看起来更先进”而过早引入过重基础设施，导致复杂度先于业务增长。这个项目现在最大的价值是业务链路已经打通，所以重构应该优先解决真实瓶颈，比如状态共享、可观测性和测试，而不是一上来就把所有东西拆成微服务。架构升级一定要跟实际负载和团队维护能力匹配。

### 源码定位

- `backend/app/core/container.py`
- `backend/app/agent/tools/registry.py`
- `apps/web/src/hooks/useChatSessionController.ts`

---

## 27. 高频知识点详解：概念、应用、追问方向

这一节不再只列关键词，而是把面试里常见的知识点拆成三部分：

- 概念：这个词在工程里到底指什么。
- 在本项目中的应用：Arcadegent 具体是怎么落地的。
- 面试可继续展开：面试官最容易从这里继续深挖什么。

### 27.1 分层架构

概念：分层架构是把系统按职责拆成若干层，每层只关注自己该做的事。常见分层包括接口层、应用层、领域层、基础设施层。这样做的目标是降低耦合，让变化集中在某一层，而不是牵一发动全身。

在本项目中的应用：后端大致分成 API 层、组合根与生命周期层、Agent 运行时层、工具与服务层、数据基础设施层。前端则分成组件视图层、状态层、控制器层和 API 调用层。比如 `chat.py` 主要负责收发请求，`react_runtime.py` 负责业务编排，`local_store.py` 和 `supabase_repository.py` 负责数据实现，这就是典型的职责分离。

面试可继续展开：为什么这样分层、每层边界怎么定义、跨层调用要避免什么、如果以后换数据库或换前端框架哪些层会受影响。

### 27.2 组合根与依赖注入

概念：组合根是系统中集中构造依赖对象的地方，依赖注入是把对象的依赖从外部传入，而不是在类内部自己创建。它们一起解决“对象怎么创建、在哪创建、由谁持有”的问题。

在本项目中的应用：`build_container` 会统一构造 `store`、`replay_buffer`、`session_store`、`tool_registry`、`provider_adapter`、`react_runtime` 和 `orchestrator`。API 层通过 `get_container` 从 `app.state` 读取这些长生命周期对象，而不是在路由里直接 new。这样测试时更容易替换 mock，实现也更清晰。

面试可继续展开：为什么 `build_container` 可以视为组合根、这种方式和 Spring 这类强依赖注入框架有什么异同、如果对象越来越多该如何继续管理。

### 27.3 Repository Pattern

概念：Repository Pattern 用来隔离“业务如何读写数据”和“数据究竟存在哪里、怎么查出来”。上层依赖仓储接口，不依赖具体数据库或文件格式。

在本项目中的应用：`ArcadeRepository` 抽象了机厅搜索和详情读取能力，底层既可以是本地 JSONL 的 `LocalArcadeStore`，也可以是 Supabase RPC 的 `SupabaseArcadeRepository`。这样 API 层和 Agent 工具层不需要知道现在是本地文件还是远程数据库。

面试可继续展开：这种抽象为什么适合读多写少系统、如果业务开始有复杂写入是否还要保持同样的接口、仓储模式和直接在 service 里写 SQL 的 trade-off 是什么。

### 27.4 Provider Pattern

概念：Provider Pattern 是把同一类能力封装成多个提供者，由统一注册表做发现和路由。它适合处理“能力来源多样，但对上层暴露接口尽量统一”的场景。

在本项目中的应用：工具系统里同时存在 builtin provider 和 MCP provider。`ToolRegistry` 不关心工具来自哪里，只关心 descriptor、schema、权限和执行入口，这让内建工具和外部工具都能走一套调用流程。

面试可继续展开：什么时候用 provider 比简单字典更划算、如何设计 descriptor、provider 模式和插件机制的关系是什么。

### 27.5 ASGI 与异步 IO

概念：ASGI 是 Python 异步 Web 应用接口标准，支持 HTTP、WebSocket 和长连接。异步 IO 不是让代码“更快”，而是在等待网络或磁盘时不阻塞线程，从而提升并发处理能力。

在本项目中的应用：后端需要同时调用 LLM、地图服务、Supabase RPC，并且要维持 SSE 长连接。FastAPI 跑在 ASGI 模型上，`httpx` 等异步调用可以减少外部请求阻塞带来的线程浪费，这对流式会话尤其重要。

面试可继续展开：异步适合什么、不适合什么；CPU 密集任务为什么不能只靠 async；async/await、事件循环和线程池之间如何协同。

### 27.6 Pydantic 与显式 Schema

概念：Schema 是接口契约，Pydantic 是 Python 里常用的数据校验与序列化工具。它的价值不仅是“字段有类型”，更是把请求、响应和内部结构变成可验证、可维护的模型。

在本项目中的应用：聊天请求、响应、会话快照和工具参数都通过模型或 schema 约束。这样前端传来的 payload、后端写入的 state、返回的 JSON 结构都更稳定，减少“字段名写错还能运行到一半才报错”的问题。

面试可继续展开：Pydantic 和 dataclass 的区别、为什么显式 schema 对 Agent 系统更重要、schema 演进时如何兼容旧数据。

### 27.7 SSE

概念：SSE 是 Server-Sent Events，基于 HTTP 的单向流式推送协议。浏览器通过 `EventSource` 长连接接收服务器不断推送的事件，适合“服务端持续通知，客户端主要监听”的场景。

在本项目中的应用：聊天不是一次性返回，而是先派发 session，再通过 `/api/stream/{session_id}` 持续推送 `session.started`、`assistant.token`、`navigation.route_ready`、`assistant.completed` 等事件。前端接收这些事件后，边更新文本边刷新地图。

面试可继续展开：为什么这里 SSE 比 WebSocket 更合适、SSE 的局限是什么、浏览器断线重连和代理层超时如何处理。

### 27.8 Event Replay 与幂等恢复

概念：Event Replay 是把过程事件按序缓存起来，在客户端断线后继续补发。幂等恢复强调“多次恢复同一状态不会造成重复副作用”，是流式系统稳定性的关键。

在本项目中的应用：后端维护 `ReplayBuffer`，前端断线重连时可以根据 `Last-Event-ID` 或 `last_event_id` 继续拉后续事件。同时，前端还会重新请求 session 快照，确保最终看到的是稳定状态，而不是仅依赖过程 token。

面试可继续展开：过程事件和最终快照为什么要同时存在、回放缓存放内存的局限是什么、多实例下 replay 怎么设计。

### 27.9 Session 级并发控制

概念：并发控制是为了解决多个请求同时修改同一资源时的一致性问题。Session 级并发控制就是把“同一个会话只能有一个运行任务”作为系统约束。

在本项目中的应用：`Orchestrator` 用 `_active_sessions` 和 `Lock` 保证同一个 `session_id` 不会被并发执行两次。这样可以避免同一轮会话同时写 memory、刷事件流、改 turns，导致结果互相污染。

面试可继续展开：这种内存锁方案适合什么规模、如果是多进程或多副本环境怎么办、乐观锁和悲观锁分别适合什么场景。

### 27.10 ReAct

概念：ReAct 是 Reason + Act，把推理和行动交替起来。模型不是一口气直接回答，而是先思考下一步该做什么，再调用工具拿 observation，再继续推理，直到收敛出最终答案。

在本项目中的应用：Arcadegent 的任务天然是多步骤的，比如识别用户想找附近机厅、根据定位搜索、必要时做地理补全、生成路线、最后再组织成自然语言回复。`ReactRuntime` 让工具执行和模型推理交替进行，更适合这种业务链路。

面试可继续展开：ReAct 和纯 prompt chaining 的区别、什么时候不需要 ReAct、如何处理死循环和长链路失败。

### 27.11 Working Memory

概念：Working Memory 是 Agent 在一次会话中维护的结构化中间态，类似“当前脑内草稿本”。它通常包含用户请求、工具观察结果、候选对象、路线、最终回复等信息。

在本项目中的应用：session state 的 `working_memory` 里会保存 `shops`、`shop`、`route`、`destination`、`client_location`、`reply`、`artifacts` 和 `worker_runs` 等结构。它既供模型读取，也供工具和 API 输出复用，避免信息散落在多个对象里。

面试可继续展开：为什么不把字段全平铺在 session 顶层、working memory 应该保存什么不该保存什么、长会话下 memory 膨胀如何处理。

### 27.12 Context Engineering

概念：Context Engineering 不是单纯写提示词，而是系统性设计“模型在每一步能看到什么信息、按什么顺序看到、哪些信息需要弱化或强化”。它更关注上下文组织，而不是一句神奇 prompt。

在本项目中的应用：`ContextBuilder` 会把请求、历史 turn、session state、技能片段和上下文块组织成更适合模型阅读的结构，而不是在运行时里随手拼字符串。文档里提到的 `directory + detail block` 思路，本质就是在控制模型注意力分配。

面试可继续展开：Context Engineering 和 template agent 有什么区别、为什么上下文顺序会影响结果、上下文窗口不够时如何裁剪。

### 27.13 Deterministic Tool 与 LLM Reasoning 分离

概念：Deterministic Tool 指输出应尽量稳定、可复现的工具能力，比如数据库查询、距离计算、坐标转换；LLM Reasoning 则更适合负责意图判断、信息整合和自然语言表达。把两者分开，是为了让不确定性只留在真正需要语言理解的地方。

在本项目中的应用：机厅搜索、逆地理、路线规划、schema 校验、坐标转换等都交给工具和服务实现；模型负责决定什么时候调用这些能力，以及最后如何把结构化结果解释给用户听。这让系统更可测，也更容易定位错误来源。

面试可继续展开：为什么不能让模型直接算距离或拼地图 HTML、这种分工会不会让流程变复杂、哪些任务必须坚持走 deterministic path。

### 27.14 JSON Schema Tool Calling

概念：JSON Schema 是用来定义 JSON 数据结构的标准，可以约束字段类型、必填项、枚举值和嵌套结构。对 Agent 来说，它相当于工具参数的正式说明书。

在本项目中的应用：工具注册表在工具执行前会按 schema 校验模型给出的参数。如果字段缺失、类型不对、枚举不合法，就能在调用前拦下来，而不是把错误拖到工具内部。对模型来说，这也相当于一个“怎样调用工具”的明确边界。

面试可继续展开：为什么 schema 能提升稳定性、schema 太严格和太宽松各有什么问题、模型多次调用工具失败时怎么做回退。

### 27.15 MCP

概念：MCP 是 Model Context Protocol，一种让模型通过统一协议接入外部工具和上下文资源的方式。它的价值在于把“模型如何发现工具、调用工具、读取能力描述”标准化。

在本项目中的应用：地图相关或外部能力可以通过 MCP provider 接入 `ToolRegistry`。这意味着系统既能保留自研 builtin tool，也能增量接入协议化的外部工具，不必把所有能力都硬编码进项目主体里。

面试可继续展开：MCP 和普通 HTTP API 封装有什么区别、什么时候应该用 MCP、MCP 工具异常时如何做降级。

### 27.16 OpenAI-compatible Provider Adapter

概念：Provider Adapter 是适配器模式在模型层的应用，核心目的是对业务层屏蔽不同 LLM 提供方的接入差异。OpenAI-compatible 则表示多家服务可以共用相近的请求协议。

在本项目中的应用：Arcadegent 不把某家模型 SDK 写死在业务里，而是通过 `ProviderAdapter` 和配置层把接入统一起来。这样切换 OpenAI、DeepSeek 或其他兼容提供方时，改动主要集中在配置和适配层。

面试可继续展开：统一接口和能力差异如何平衡、为什么抽象层不能只做“统一 URL”、模型切换时最容易踩什么坑。

### 27.17 SPA

概念：SPA 是 Single Page Application，首屏加载后主要在浏览器内完成路由切换、状态更新和界面刷新。它适合高交互、低页面跳转成本的产品形态。

在本项目中的应用：机厅浏览、聊天流式回复、地图交互、会话恢复都强依赖浏览器内状态和持续交互，因此 React + Vite 的 SPA 方案比较自然。前端不需要频繁整页刷新，而是根据 SSE 和 API 响应局部更新界面。

面试可继续展开：SPA 对 SEO 的代价是什么、为什么这个项目不优先选 SSR/Next.js、一体化框架和 API-first 分离架构怎么取舍。

### 27.18 Zustand

概念：Zustand 是轻量级状态管理库，适合中等规模全局状态。它比 Redux 样板更少，又比纯 Context 更适合高频更新和跨组件共享状态。

在本项目中的应用：`appStore` 管聊天会话、流式状态和地图 artifacts，`arcadeBrowserStore` 管机厅浏览器的筛选、分页和地图运行时。这样比把所有逻辑塞进组件 state 或 Context 更清晰，也利于前端逐步演进。

面试可继续展开：为什么不用 Redux、什么时候 Zustand 也会失控、如何避免 store 变成“上帝对象”。

### 27.19 Hook/Controller 分层

概念：前端 controller/hook 分层，是把视图组件里的副作用和流程编排抽离出去，让组件主要负责展示。它本质上是在 React 世界里做应用层与视图层解耦。

在本项目中的应用：`useChatSessionController` 负责创建会话、连接 EventSource、消费事件、刷新详情和处理恢复逻辑；组件只消费 store 状态并渲染 UI。这样后续要换界面样式时，不会把流程控制一起改乱。

面试可继续展开：controller hook 和普通 custom hook 的差别是什么、哪些逻辑应该进 hook、哪些逻辑仍然应该留在组件里。

### 27.20 Markdown 渲染与 XSS

概念：Markdown 渲染是把模型输出的富文本转换成 HTML 展示；XSS 是跨站脚本攻击，如果未经清洗直接渲染 HTML，恶意脚本可能在浏览器执行。

在本项目中的应用：前端使用 `marked` 和 `DOMPurify`。前者把 Markdown 转成 HTML，后者在注入 DOM 前做清洗。这样既保留大模型文本展示能力，也降低直接渲染内容带来的安全风险。

面试可继续展开：为什么不能只信任模型输出、DOMPurify 解决什么、还有哪些安全边界需要前后端同时控制。

### 27.21 Haversine

概念：Haversine 是球面两点距离的近似计算公式，适合用经纬度估算地表两点直线距离。它不是导航路径距离，但足够支持“附近排序”这类场景。

在本项目中的应用：本地 JSONL 仓储在没有地图导航服务参与时，用 Haversine 对候选门店做距离排序。这样用户搜索“附近机厅”时，即便在轻量模式下也能拿到基本可信的附近结果。

面试可继续展开：为什么不能直接做经纬度差值、Haversine 和真实路线距离的差异是什么、什么时候必须接专业路线服务。

### 27.22 WGS84 与 GCJ-02

概念：WGS84 是全球通用的 GPS 坐标系，GCJ-02 是中国境内常见互联网地图使用的加密偏移坐标系。两者不能混用，否则地图点位会出现明显偏差。

在本项目中的应用：浏览器定位更接近原始定位语义，而高德地图展示依赖 GCJ-02，因此前端在靠近展示层的位置做坐标转换。这样既能保留源数据语义，也能保证地图渲染正确。

面试可继续展开：为什么不在后端统一转换、不同地图服务切换时如何处理、定位、展示、路线规划是否应该全部使用同一坐标语义。

### 27.23 Structured Artifacts

概念：Structured Artifacts 指前后端约定一套结构化视图数据，而不是让模型直接输出 HTML 或组件代码。它强调“数据和表现分离”。

在本项目中的应用：地图相关内容通过 `shops`、`route`、`destination`、`view_payload` 等结构发给前端，再由 React 组件渲染成地图卡片和路线视图。这样前端可以牢牢掌控交互与安全边界。

面试可继续展开：为什么结构化 artifacts 比模型直出 HTML 更稳、这种契约如何演进、文本内容和强结构化内容为什么要区别处理。

### 27.24 JSONL 读模型

概念：读模型是为了高效读取而设计的数据组织方式，不一定等于系统真实主存储。JSONL 读模型则是把一条条结构化记录按行存储，方便导入、调试和离线处理。

在本项目中的应用：本地开发模式下，项目启动后把 JSONL 读入内存，并基于字段构建 `search blob` 之类的搜索辅助结构。这样在没有数据库的情况下也能跑搜索、筛选和附近排序。

面试可继续展开：为什么 JSONL 适合早期阶段、数据量增大后瓶颈在哪、它和 SQLite / Postgres / Elasticsearch 的边界如何划分。

### 27.25 Supabase RPC

概念：RPC 是把数据库侧逻辑包装成稳定函数接口，而不是让调用方直接拼接底层表查询。它更适合把筛选、排序和兼容逻辑集中管理在服务端。

在本项目中的应用：Supabase 模式下，后端通过 RPC 读取机厅数据，而不是把数据库表结构直接泄露给前端。这样业务侧只依赖“拿到什么结果”，不依赖“底表怎么长”，接口边界更稳。

面试可继续展开：RPC 和 PostgREST 表查询各自适合什么、为什么后端服务读模型更偏向 RPC、SQL 逻辑放库内和放应用层的 trade-off 是什么。

### 27.26 Docker Compose

概念：Docker Compose 是多容器本地编排工具，用来统一定义服务、网络、环境变量和启动方式。它特别适合多服务项目的开发联调和中小规模部署。

在本项目中的应用：Arcadegent 用 Compose 把后端 FastAPI 服务和前端 Nginx 静态站点一起编排起来。这样开发者只要按统一入口启动，就能拉起完整系统，不需要手工逐个配置网络和端口。

面试可继续展开：为什么 Compose 适合当前阶段、和 Kubernetes 这类平台有什么定位差异、从 Compose 迁移到生产平台时最先要拆的是什么。

### 27.27 测试金字塔在 LLM/Agent 项目里的变形

概念：传统测试金字塔强调单元测试最多、集成测试其次、E2E 最少。到了 LLM/Agent 系统里，这个原则仍然成立，但断言重点会从“文本逐字一致”转向“结构、状态迁移、工具调用和错误处理一致”。

在本项目中的应用：后端可以单测距离、仓储、坐标或工具逻辑；集成层验证 API 和 session 流转；前端 Playwright 验证聊天与地图交互。真正涉及 LLM 输出时，更适合验证 schema、事件顺序、artifact 是否正确，而不是逐字对比回答。

面试可继续展开：为什么 Agent 测试更难、什么应该 mock 什么应该打真服务、如何设计稳定的回归用例。

### 27.28 可观测性

概念：可观测性是让你在系统出问题时，能够通过日志、指标和追踪理解系统内部发生了什么。它不是单纯“把错误打印出来”，而是为排障和容量分析建立观察面。

在本项目中的应用：对 Arcadegent 来说，最值得观测的是工具调用耗时、LLM 耗时、session 生命周期、SSE 活跃连接数、失败类型、地图服务错误和 replay buffer 使用情况。这些指标能帮助判断瓶颈究竟在模型、外部服务还是本地状态管理。

面试可继续展开：应该打哪些日志、哪些指标最先做、单次会话如何串起端到端追踪、为什么 Agent 系统比 CRUD 更依赖可观测性。

### 27.29 Graceful Degradation

概念：Graceful Degradation 是优雅降级，意思是局部能力失效时，系统退化但不完全崩溃。它关注的不是“永不失败”，而是“失败后还保持可用”。

在本项目中的应用：如果 MCP 工具不可用，核心搜索和会话流仍然应该可运行；如果地图路线失败，也应尽量返回文本说明或基础门店结果，而不是整轮会话直接报废。对于依赖外部地图和模型服务的项目，这种降级意识非常重要。

面试可继续展开：哪些能力必须降级、哪些能力失败就该直接报错、降级策略如何和产品体验结合。

---

## 28. 建议单独背熟的知识点清单

如果时间不够，下面这些概念至少要能做到“不看文档也能讲出定义、应用和优缺点”。

- FastAPI 的 `lifespan`、依赖注入和 ASGI 异步模型
- SSE、`EventSource`、`Last-Event-ID` 和事件回放
- ReAct、working memory、LoopGuard、context engineering
- Repository pattern、provider pattern、组合根
- JSON Schema 工具校验、MCP、OpenAI-compatible provider adapter
- Zustand、controller hook 分层、Markdown 渲染和 XSS 防护
- Haversine、WGS84 / GCJ-02、structured artifacts
- JSONL 读模型、Supabase RPC、Docker Compose
- LLM/Agent 项目的测试策略、可观测性和优雅降级

---

## 29. 一面和二面回答策略

### 一面建议

- 优先讲业务闭环，不要一上来只背框架名。
- 每个问题尽量按“为什么这样设计 -> 解决了什么问题 -> 代价是什么”来答。
- 遇到追问时，多用“当前阶段”和“如果规模上来会怎么演进”的表述，能体现判断力。

### 二面建议

- 主动讲清 trade-off，比如 SSE 为什么够用、JSONL 为什么只适合早期、为什么要保留 OpenAI-compatible 抽象。
- 不要只说“我用了某技术”，要说“我为什么不用另一个方案”。
- 对单实例局限、Agent 非确定性、外部依赖不稳定这些问题要诚实，面试官通常更看重你有没有风险意识。

---

## 30. 建议的复习顺序

1. 背熟“30 秒项目介绍”。
2. 重点准备第 3、5、8、11、14、19、24、25 节。
3. 对每个问题再练一遍“深度追问回答”。
4. 面试前最后看一遍源码定位，确保能把回答和实现对应起来。

---

## 31. 补充高频问题：健康检查为什么不是只返回 ok

### 可能问题

你们的 `/health` 为什么不只是返回一个 `ok` 字符串？

### 相关知识点：概念及应用

健康检查：
健康检查是服务对外暴露的“我现在是否可用”的接口，但它通常不只回答“进程活着没有”，还可以回答关键依赖是否就绪。

Liveness 与 Readiness：
`liveness` 更偏“进程有没有死”，`readiness` 更偏“服务能不能接流量”。很多系统会把两者拆开，但轻量系统也可能先合并成一个统一健康端点。

依赖健康聚合：
对依赖较多的系统来说，只返回 200 和 `ok` 价值不大，因为真正的故障往往不在进程本身，而在外部服务、数据加载或工具发现。

在本项目中的应用：
Arcadegent 的 `/health` 会返回数据源健康、环境、tool provider 状态和 MCP discovery 状态，而不只是返回存活标记。这样排查时能更快判断问题出在 JSONL/Supabase、MCP 工具发现，还是运行环境配置。

### 参考回答

因为这个项目的可用性不只取决于进程是否活着，还取决于数据源是否加载成功、工具提供者是否可用、MCP 工具是否发现成功。如果 `/health` 只返回一个 `ok`，运维和开发者并不能判断系统有没有真正进入可服务状态。现在的设计更接近轻量版 readiness，能直接暴露数据和工具链路的状态。

### 深度追问

那为什么不直接拆成 `/live` 和 `/ready`？

### 深度追问回答

从规范上讲，拆开会更标准，尤其在 Kubernetes 这类环境里更常见。当前项目还处于相对轻量阶段，用一个聚合健康端点能降低实现复杂度，同时满足本地联调和中小规模部署的排障需求。如果未来上更正式的平台，我会把“进程存活”和“依赖就绪”拆成两个端点，并为每种依赖定义更明确的失败语义。

### 源码定位

- `backend/app/api/http/health.py`
- `backend/app/core/lifecycle.py`
- `backend/app/tests/integration/test_api.py`

---

## 32. 补充高频问题：为什么浏览器定位和逆地理编码要拆成前后端两段

### 可能问题

为什么不让前端直接调用高德逆地理，而是浏览器拿坐标、后端做 reverse geocode？

### 相关知识点：概念及应用

浏览器定位：
浏览器定位的职责是向用户申请权限并拿到当前经纬度，它更像“终端能力”。

逆地理编码：
逆地理编码是把经纬度转换成省、市、区、街道、格式化地址等语义信息，它更像“服务能力”。

密钥隔离：
只要涉及第三方服务 key，就要优先考虑不要把 key 暴露给浏览器。

职责分离：
把“采集坐标”和“解析地区信息”拆开，能让前端只处理用户授权和缓存，后端只处理第三方地图服务调用。

在本项目中的应用：
前端负责 `navigator.geolocation` 与本地缓存；后端通过高德 REST 接口完成逆地理，并把解析结果回注到 `ChatRequest.location` 和 session memory 中，供 Agent 直接消费。

### 参考回答

因为这两件事的边界本来就不同。定位必须在浏览器里完成，因为要拿用户授权；逆地理编码更适合放在后端，因为它依赖高德 API key，而且解析结果本质上是业务上下文，不只是前端展示数据。拆开之后，前端更轻，后端更安全，也更利于把地区信息统一注入 Agent 上下文。

### 深度追问

如果高德逆地理失败了，对话还能继续吗？

### 深度追问回答

可以继续。项目的设计是“定位或逆地理失败只降级，不阻塞聊天”。最差情况下，只是会缺失地区文本信息，Agent 少了一些上下文，但搜索、问答和会话流程仍然可走通。这其实就是把逆地理设计成增强项，而不是硬依赖。

### 源码定位

- `docs/dev-details/browser-location-reverse-geocoding.md`
- `backend/app/api/http/location.py`
- `backend/app/services/amap_reverse_geocoder.py`
- `apps/web/src/lib/clientLocation.ts`

---

## 33. 补充高频问题：工具权限策略为什么是必要的

### 可能问题

既然 subagent 已经有 `allowed_tools`，为什么还要有单独的 `ToolPermissionChecker` 和 policy 文件？

### 相关知识点：概念及应用

Allow List：
`allowed_tools` 是运行时范围控制，表示当前 subagent 这一轮理论上能调用哪些工具。

Policy：
policy 更像全局治理规则，用来声明某个工具是否只读、是否并发安全、MCP 是否允许通配等。它比单次运行时 allow list 更偏平台层。

最小权限原则：
Agent 系统里最危险的点之一就是模型调用了不该调用的能力，因此权限边界不应只存在一处，而应该分层防守。

在本项目中的应用：
subagent profile 里声明了 allowed tools，`ToolPermissionChecker` 又会在执行前再次检查工具是否被允许，并从 `tool_policies.yaml` 读取全局规则。这是“运行时授权 + 全局策略”的双层设计。

### 参考回答

因为 `allowed_tools` 只解决“当前这个 agent 角色理论上能用哪些工具”，但它不是全局治理机制。单独的权限检查器和 policy 文件是为了把工具安全边界显式化，让运行时授权和平台级策略分开。这样即使后续工具来源更多、角色更多，权限规则仍然能集中管理，而不是散落在 prompt 或代码分支里。

### 深度追问

如果以后引入可写工具，这套权限体系还够吗？

### 深度追问回答

目前这套体系更偏只读工具设计，代码里也明确写了“当前工具默认只读”。如果以后引入写操作工具，我会把 policy 扩展成更强的能力描述，比如读写级别、危险级别、是否要求人工确认、是否允许并发，以及审计日志字段。也就是说，现在的权限检查是一个可扩展的钩子，不是最终形态。

### 源码定位

- `backend/app/agent/tools/permission.py`
- `backend/app/agent/nodes/profiles/tool_policies.yaml`
- `backend/app/agent/subagents/subagent_builder.py`

---

## 34. 补充高频问题：为什么需要 provider profile

### 可能问题

为什么模型配置不直接全写在环境变量里，还要单独有 provider profile？

### 相关知识点：概念及应用

配置分层：
环境变量适合运行环境差异，profile 适合“同一环境下的策略差异”。

Profile：
profile 本质上是一组可切换的配置组合，比如模型名、超时、温度、最大 token、是否启用 provider。

策略抽象：
对 Agent 项目来说，模型配置不只是连接信息，还包含推理风格和工具调用策略，因此比传统数据库配置更值得做 profile 化。

在本项目中的应用：
`provider_profiles.yaml` 中定义了 `default`、`local`、`rule_based`、`template` 等 profile。运行时会把 profile 配置和环境变量一起解析，允许“默认行为可切换，局部参数可覆盖”。

### 参考回答

因为模型配置不仅仅是一个 API key 和 base URL，它还包括超时、温度、最大 token、是否允许工具调用、是否启用某个 provider 等策略。把这些全部塞进环境变量会让配置既分散又难理解。profile 让系统可以预定义几组运行策略，再由环境变量做必要覆盖，这样更适合 Agent 系统的多模式运行。

### 深度追问

profile 和环境变量如果冲突了，应该以谁为准？

### 深度追问回答

通常应该明确优先级。这个项目的做法是先读取 profile，再允许显式环境变量覆盖默认 profile 值。这样 profile 负责给出“策略基线”，环境变量负责处理部署时的临时或环境差异。面试时可以强调，关键不只是优先谁，而是优先级必须稳定、可预测。

### 源码定位

- `backend/app/agent/llm/llm_config.py`
- `backend/app/agent/nodes/profiles/provider_profiles.yaml`

---

## 35. 补充高频问题：geo cache 的价值是什么

### 可能问题

为什么机厅地理解析还要做本地 geo cache？

### 相关知识点：概念及应用

Cache：
缓存的核心作用是减少重复计算或重复外部请求，降低延迟和成本。

地理缓存：
当门店坐标不完整且 geocode 依赖外部地图服务时，缓存可以显著减少重复调用、限流风险和响应抖动。

精度分层：
缓存的地理数据未必都是高精度原始坐标，有时只是 geocode 的近似值，因此缓存时要保留来源和 precision 语义。

在本项目中的应用：
`ArcadeGeoResolver` 会优先用 catalog 坐标，其次查本地 cache，再不行才调用高德 geocode，并把结果带上 `source` 和 `precision` 写回 cache。这样机厅浏览器和聊天地图不会每次都打外部地图服务。

### 参考回答

因为很多门店数据源并不总是自带完整坐标，如果每次展示列表都实时 geocode，会带来明显的外部依赖成本和不稳定性。加上 geo cache 后，第一次补全之后后续就能直接复用，既减少接口耗时，也降低地图服务限流和失败带来的影响。这对一个读多写少的机厅检索系统很实用。

### 深度追问

缓存失效和错误缓存怎么处理？

### 深度追问回答

关键是缓存 key 不能只靠门店名，而要结合地址、更新时间或来源信息做更稳定的指纹。这个项目里会记录 `updated_at` 和地址指纹，并在写入时清掉同一 `source_id` 的旧 key。面试时可以进一步补充，如果业务复杂度更高，还应该引入 TTL、版本号或人工校验机制，避免错误 geocode 长期污染结果。

### 源码定位

- `backend/app/services/arcade_geo_resolver.py`
- `backend/app/services/arcade_payload_mapper.py`

---

## 36. 补充高频问题：为什么 `summary_tool` 还在，但不再做主回答路径

### 可能问题

既然文档说不要做 template agent，为什么 `summary_tool` 还保留着？

### 相关知识点：概念及应用

兼容性保留：
系统演进时，旧能力不一定立刻删除，有时会先降级成兼容或兜底路径。

Deterministic Formatter：
摘要工具如果只是把结构化结果按固定规则格式化，它本质上还是工具，而不是完整推理器。

主路径与辅助路径：
主路径决定系统设计方向，辅助路径则可以为兼容、回退或特殊场景保留。

在本项目中的应用：
文档明确说明最终回答应主要由 agent 基于 context 和 skill 生成，而不是依赖 `summary_tool` 模板兜底。`summary_tool` 还保留，是为了兼容和 deterministic formatting，而不再承担核心回答职责。

### 参考回答

因为系统演进不是非黑即白。`summary_tool` 还保留，说明它在某些兼容场景或确定性格式化场景仍有价值，但它不再是主回答路径。主路径已经转到“Agent 读结构化上下文并组织回答”，这才是架构方向。换句话说，保留工具不代表依赖工具，只是给系统留了一个稳定的兼容和回退能力。

### 深度追问

什么时候你会彻底删除 `summary_tool`？

### 深度追问回答

当两个条件都满足时我才会删：第一，所有主流程和边缘流程都不再依赖它兜底；第二，Agent 基于 context 和 skill 的回答质量已经足够稳定，且有测试和线上观察数据支撑。如果还存在某些强格式输出场景需要 deterministic formatting，那它可能仍然值得保留，只是职责要非常明确。

### 源码定位

- `docs/dev-details/agent-context-payload-design.md`
- `backend/app/agent/tools/builtin/summary_tool.py`
- `backend/app/agent/runtime/react_runtime.py`

---

## 37. 补充高频问题：这个项目存在跨域吗

### 可能问题

这个项目存在跨域吗？如果有，是怎么处理的？

### 相关知识点：概念及应用

同源策略：
浏览器默认要求协议、域名、端口都相同才算同源。只要三者之一不同，浏览器就会把请求视为跨源请求，并应用更严格的安全限制。

CORS：
CORS 是浏览器上的跨源资源共享机制，本质上是服务端通过响应头声明“哪些来源可以访问我”。它不是后端之间的限制，而是浏览器安全模型的一部分。

反向代理规避跨域：
如果前端页面和后端 API 最终都从同一个域名下访问，比如页面请求 `/api/...`，由 Nginx 在服务端转发到后端，那么从浏览器视角看就是同源请求，不会触发前端跨域问题。

开发代理：
开发时常用 Vite/Webpack dev server 代理，把 `/api` 请求转发到后端。这样虽然真实后端在另一个端口，但浏览器仍然只看到当前前端域名，因此同样规避了浏览器跨域。

在本项目中的应用：
这个项目要分场景看。

1. 开发态默认配置下：
前端跑在 `http://127.0.0.1:5173`，后端跑在 `http://127.0.0.1:8000`，理论上这是跨端口、属于跨域场景。
但是 Vite 配置了 `/api` 和 `/health` 代理到后端，所以浏览器实际请求的是当前前端地址下的 `/api/...`，通常不会直接触发浏览器跨域报错。

2. 开发态直接请求后端时：
如果前端把 `VITE_API_BASE` 显式配成 `http://127.0.0.1:8000` 或其他绝对地址，那浏览器就会直接跨源访问后端，这时需要后端 `CORSMiddleware` 放行对应 origin。项目里通过 `CORS_ALLOW_ORIGINS` 配置了这一层兼容。

3. 生产态默认部署下：
前端由 Nginx 托管静态资源，`/api`、`/api/stream/`、`/health` 都由同一个 Nginx 反向代理到 backend。从浏览器视角看通常是同域下的路径访问，因此默认是“同源访问”，不构成前端跨域问题。

4. 分域部署或误配置场景：
如果生产上把前端和后端拆到不同域名、不同端口，或者 `VITE_API_BASE` 指向了另一个绝对地址，那么就会重新出现浏览器跨域问题，需要正确配置 CORS，并确保 SSE 流接口也能被该 origin 访问。

### 参考回答

这个项目不是简单地“有跨域”或“没有跨域”，而是分场景。开发阶段前后端端口不同，理论上存在跨域可能，但默认通过 Vite 代理规避了浏览器层的跨域；如果前端直接请求后端绝对地址，就需要后端 CORS 放行。生产默认部署下，Nginx 把前端静态资源和 `/api` 路径统一到同一个域名下，对浏览器来说通常是同源访问，所以一般没有前端跨域问题。

### 深度追问

那既然开发态已经有 Vite 代理，为什么后端还要配 `CORSMiddleware`？

### 深度追问回答

因为代理只覆盖“按既定方式开发”的默认路径，但系统并不能假设所有调用都永远经过 Vite 代理。比如前端显式配置了 `VITE_API_BASE` 指向后端绝对地址、Playwright 或其他调试方式绕过代理、未来前后端独立域名部署，这些都会重新触发浏览器跨域。后端保留 `CORSMiddleware`，相当于给系统提供了直接跨源访问的正式兼容层，而不是把跨域可用性完全寄托在开发代理上。

### 深度追问

SSE 流接口也会受跨域影响吗？

### 深度追问回答

会。`EventSource` 本质上仍是浏览器发起的 HTTP 请求，所以同样遵守同源策略和 CORS 规则。这个项目生产环境里专门通过 Nginx 把 `/api/stream/` 反向代理到 backend，并关闭 buffering、调高超时，既是为了解决 SSE 长连接体验，也是为了尽量让前端以同源路径访问流接口，减少跨域和代理层问题。

### 源码定位

- `apps/web/vite.config.ts`
- `backend/app/main.py`
- `apps/web/nginx.conf`
- `apps/web/src/api/client.ts`
- `README.md`

---

## 38. 补充高频问题：SSE 是怎么实现的

### 可能问题

这个项目里的 SSE 是怎么实现的？前后端分别做了什么？

### 相关知识点：概念及应用

SSE：
SSE，全称 Server-Sent Events，是基于 HTTP 的服务端单向推送协议。浏览器通过 `EventSource` 建立长连接，服务端不断按固定格式输出事件，客户端持续接收。

事件格式：
标准 SSE 消息通常包含 `id`、`event` 和 `data` 三部分，例如：

```text
id: 12
event: assistant.token
data: {"delta":"你好"}
```

浏览器消费模型：
前端不需要自己手写 socket 协议，直接使用 `EventSource(url)` 即可订阅服务端事件，并按事件名监听不同消息。

事件回放：
SSE 原生支持 `Last-Event-ID`，断线后可从上次接收的事件位置继续恢复，这很适合会话型流式输出。

长连接代理要求：
SSE 虽然基于 HTTP，但它不是普通短请求，所以反向代理层要关闭 buffering，并提高读写超时，否则流会被缓存或提前断开。

在本项目中的应用：
Arcadegent 的 SSE 不是单独凭空推消息，而是和异步会话派发结合。

1. 前端先调用 `POST /api/chat/sessions`，拿到 `session_id`。
2. 后端用 `Orchestrator.dispatch_chat()` 在后台创建聊天任务。
3. `ReactRuntime` 在执行过程中不断往 `ReplayBuffer` 追加事件，比如：
   - `session.started`
   - `subagent.changed`
   - `tool.*`
   - `navigation.route_ready`
   - `assistant.token`
   - `assistant.completed`
   - `session.failed`
4. 前端再通过 `EventSource(/api/stream/{session_id})` 订阅该 session 的事件流。
5. 后端 `/api/stream/{session_id}` 接口循环读取 replay buffer，把新事件格式化成 SSE 输出。
6. 前端按事件名更新界面状态：
   - token 事件更新流式回复
   - route 事件更新地图工件
   - completed 事件收口并重新拉取会话详情

### 参考回答

这个项目的 SSE 实现是“后台异步会话 + replay buffer + EventSource 消费”三段式。后端不会在聊天接口里直接把 token 边算边写回 HTTP 响应，而是先派发一个后台 session，由 `ReactRuntime` 把执行过程不断写入 `ReplayBuffer`。然后 `/api/stream/{session_id}` 这个接口以 `text/event-stream` 方式持续把这些事件输出给前端。前端使用 `EventSource` 订阅流，根据 `assistant.token`、`navigation.route_ready`、`assistant.completed` 等事件分别更新文本、地图和会话状态。

### 深度追问

后端具体是怎么把普通事件变成 SSE 协议格式的？

### 深度追问回答

后端在 `sse.py` 里有一个 `_format_sse()`，会把事件名、事件 id 和 JSON 数据拼成标准 SSE 文本：

- `id: {event_id}`
- `event: {event_name}`
- `data: {json}`

每条消息之间再用空行分隔。`StreamingResponse` 会持续输出这些字符串，浏览器的 `EventSource` 就能按事件流解析。这个实现很轻量，但足够满足本项目“服务端持续推送、前端持续消费”的场景。

### 深度追问

如果暂时没有新事件，连接怎么保持不断？

### 深度追问回答

后端会定期输出 `: keep-alive` 这样的注释行作为心跳，同时 `await asyncio.sleep(sse_keepalive_seconds)` 做轮询节奏控制。这样即使短时间没有新事件，代理层和浏览器也知道连接仍然活着，不会过早断开。这个心跳机制对 SSE 很重要，尤其经过 Nginx 或其他负载均衡时更明显。

### 深度追问

SSE 断线后为什么还能恢复？

### 深度追问回答

因为项目不是把事件只写给当前连接，而是先写进 `ReplayBuffer`。流接口接受 `last_event_id` 查询参数，也会读取 `Last-Event-ID` 请求头，所以重连后后端可以从上次事件 id 之后继续补发。前端最终还会再拉一次 `GET /api/chat/sessions/{session_id}`，用稳定快照兜底，这样即使中间错过少量 token，也不会影响最终一致性。

### 深度追问

前端收到这些事件后具体做了什么？

### 深度追问回答

前端的 `useChatSessionController` 会创建 `EventSource`，然后按事件类型处理：

- `session.started`：把当前 session 标记为运行中
- `subagent.changed`：更新当前活跃 subagent
- `assistant.token`：通过 `useStreamReply` 逐步拼接流式回复
- `navigation.route_ready`：先展示路线地图卡片
- `assistant.completed`：把状态标记为完成，关闭流，并重新加载 session detail
- `session.failed`：记录错误信息并停止等待

也就是说，前端不是简单打印流文本，而是在消费一个“事件驱动的状态流”。

### 深度追问

为什么生产环境里还要专门配 Nginx？

### 深度追问回答

因为 SSE 对代理层有特殊要求。普通 HTTP 代理可能会缓冲响应，导致前端长时间看不到实时事件；也可能因为默认超时太短而切断长连接。项目里的 `nginx.conf` 对 `/api/stream/` 单独关闭了 `proxy_buffering`、关闭缓存，并把 `proxy_read_timeout` 和 `proxy_send_timeout` 调高，这样流式事件才能真正实时透传到浏览器。

### 源码定位

- `backend/app/api/http/chat.py`
- `backend/app/api/stream/sse.py`
- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/events/replay_buffer.py`
- `apps/web/src/api/client.ts`
- `apps/web/src/hooks/useChatSessionController.ts`
- `apps/web/src/hooks/useStreamReply.ts`
- `apps/web/nginx.conf`

---

## 39. 补充高频问题：这个项目存在多 Agent 协作吗

### 可能问题

这个项目里有多 Agent 协作吗？如果有，是怎么协作的？

### 相关知识点：概念及应用

Multi-Agent / 多 Agent：
多 Agent 指系统里不止一个智能体，每个智能体承担不同职责，并通过消息、任务、共享上下文或工具结果进行协作，共同完成更复杂的目标。

Hub-and-Worker 模式：
这是多 Agent 的一种常见实现方式。一个主 Agent 负责理解用户目标、拆解任务、调度合适的 worker；各 worker 只处理自己擅长的子问题。它比“所有能力都塞进一个大 Agent”更容易控制上下文和权限边界。

Subagent Profile：
Subagent profile 用来定义每个 Agent 的 prompt、可用工具、技能文件和输出约束。本质上它是“角色配置”，不是简单的名字区分。

任务委派：
多 Agent 不一定要靠多个服务进程实现，也可以在单个运行时里由主 Agent 通过某个 dispatch 工具把任务委托给 worker，再回收 worker 结果。

共享工作记忆：
多个 Agent 协作时，通常需要共享一部分状态，比如已检索到的门店、用户位置、路线结果和本轮任务上下文。但共享不等于完全共用上下文，好的设计会做必要的裁剪和晋升。

权限隔离：
多 Agent 协作的一个价值是让不同 Agent 只看到、只调用和自己职责相关的工具。例如搜索 worker 不应该天然拥有所有导航和汇总能力。

串行协作与并行协作：
多 Agent 协作不一定是并行的。串行协作指主 Agent 先判断，再调用一个 worker，worker 完成后主 Agent 再继续；并行协作则是多个 worker 同时跑，再汇总结果。

在本项目中的应用：
Arcadegent 确实存在多 Agent 协作，但更准确地说，是“单运行时里的主 Agent + worker subagent 协作”，而不是多个独立自治 Agent 并发运行。

当前角色主要有三个：

- `main_agent`：负责意图识别、任务分发和最终回复生成
- `search_worker`：负责机厅检索、列表和详情查询
- `navigation_worker`：负责目标解析、路线规划和导航结果组织

它的工作流大致是：

1. 用户请求先进入 `main_agent`
2. `main_agent` 根据意图决定是否调用 `invoke_worker`
3. 运行时根据 `worker` 参数切到 `search_worker` 或 `navigation_worker`
4. worker 只在自己的工具白名单范围内运行
5. worker 产出的 `shops`、`route`、`destination` 等 artifacts 会被提升回父级 working memory
6. `main_agent` 再基于这些结果生成用户最终看到的回复

所以它属于“有角色分工的 Agent 协作”，但不是“多个完全独立的大模型进程互相对话”的那种重型多 Agent 系统。

### 参考回答

有，但我会更准确地描述为“主 Agent 加两个 worker subagent 的协作式运行时”。`main_agent` 负责理解用户问题、判断应该搜索还是导航，并通过 `invoke_worker` 把具体任务分派给 `search_worker` 或 `navigation_worker`。worker 完成后，运行时会把门店、路线、目标点这些结构化结果提升回主会话的 working memory，最后再由主 Agent 组织成用户可见回复。

所以它已经具备多 Agent 的职责拆分、权限隔离和结果回收机制，但本质上仍是一个进程内的 hub-and-worker 架构，而不是多个自治 Agent 并行协作的平台。

### 深度追问

为什么不把所有能力都塞进一个 Agent，而要拆成主 Agent 和 worker？

### 深度追问回答

因为搜索、导航和最终回复的任务形态不一样。拆成主 Agent 和 worker 有几个好处。第一，能减少单次 prompt 的职责混杂，降低上下文污染。第二，可以给不同 worker 配不同的 allowed tools，减少误调用。第三，worker 的输出可以更结构化，比如搜索 worker 更关注 `shops` 和 `total`，导航 worker 更关注 `destination` 和 `route`。第四，后续如果要替换某个 worker 的 prompt、模型或工具集，不会影响整个系统。这个项目里 `SubAgentBuilder` 和 YAML definitions 就是在支撑这种角色化配置。

### 深度追问

这些 worker 真的是独立 Agent 吗，还是只是普通函数封装？

### 深度追问回答

它们不是简单函数封装，因为每个 worker 都有独立 profile，包括自己的 prompt 文件、allowed tools 和 skill files，运行时还会切换 `active_subagent` 并发出 `subagent.changed`、`worker.started`、`worker.completed` 这些事件。从设计上看，它们已经具备 Agent 角色边界。

但它们也不是完全自治的独立系统，因为还是运行在同一个 `ReactRuntime` 里，共享同一个 session state 和 replay buffer，调度权也掌握在主流程手上。所以更准确的说法是“subagent 协作”，而不是“多个独立服务级 Agent”。

### 深度追问

这些 Agent 之间是怎么共享上下文的？

### 深度追问回答

运行时不会把父级会话的全部状态原样塞给 worker，而是通过 `_build_worker_memory_snapshot()` 挑选必要上下文，比如 `last_request`、`keyword`、`shop`、`shops`、`route`、`client_location` 等。worker 完成后，再通过 `_promote_worker_artifacts()` 把有价值的结果提升回父级 working memory，比如 `shops`、`destination`、`route` 和 `view_payload`。这种方式比“完全共享一个大上下文对象”更可控，也更利于后续演进。

### 深度追问

它支持真正的并行多 Agent 吗？

### 深度追问回答

从当前实现看，不属于真正的并行多 Agent。它的协作过程主要是串行的：主 Agent 决策，worker 执行，主 Agent 汇总。代码里虽然有 `worker_runs`、`worker_run_id` 和丰富的 worker 事件，但没有看到同一轮里多个 worker 并行 fan-out 再 fan-in 汇总的调度器设计。

这其实很合理，因为当前业务更偏“搜索一次”或“规划一次路线”的线性任务，串行协作更简单、可观测性更好。如果以后要扩展成真正的并行多 Agent，可以考虑让多个 worker 同时执行候选搜索、路线比对或多数据源查询，再由主 Agent 聚合结果。

### 深度追问

多 Agent 架构在这个项目里的主要收益是什么？

### 深度追问回答

最大的收益是职责清晰和可控性更强。搜索 worker 可以专注结构化检索，导航 worker 可以专注路线和地理信息，主 Agent 只做编排和答复。这种拆分让 prompt 更短、工具权限更窄、问题定位更容易，SSE 里还能明确看到当前活跃的是哪个 subagent。对一个带工具调用和地图路线的 Agent 应用来说，这比单个“大一统 Agent”更容易维护。

### 深度追问

如果面试官继续问“这算不算真正的 multi-agent”，应该怎么回答更稳？

### 深度追问回答

比较稳的回答是：算，但属于轻量级、多角色、单运行时的 multi-agent 协作，而不是多个自治智能体组成的分布式 multi-agent 平台。也就是说，它已经具备角色拆分、任务委派、工具隔离和结果汇总这些多 Agent 核心特征，但没有做到独立进程、独立记忆、并行博弈或复杂协商。

这种回答既承认了项目的协作设计，也不会把架构说得过重，更符合当前代码实际。

### 源码定位

- `backend/app/agent/subagents/subagent_builder.py`
- `backend/app/agent/nodes/definitions/intent.yaml`
- `backend/app/agent/nodes/definitions/query.yaml`
- `backend/app/agent/nodes/definitions/navigation.yaml`
- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/tools/builtin/schemas/invoke_worker.json`
- `backend/app/agent/tools/builtin/executors/invoke_worker.py`
- `README.md`

---

## 40. 补充高频问题：ReAct 在这个项目里是怎么实现的

### 可能问题

你们说后端是 ReAct 风格运行时，那它在代码里到底是怎么实现的？

### 相关知识点：概念及应用

ReAct：
ReAct 是 Reason + Act，核心思想是让模型在“推理”和“行动”之间交替推进。模型先根据当前上下文决定下一步做什么，如果需要外部信息，就发起 tool call；拿到 observation 后再继续推理，直到可以给出最终答案。

Tool Calling：
Tool calling 指模型不只输出自然语言，还能输出结构化工具调用请求。运行时收到这些请求后，执行真实工具，再把结果作为 observation 反馈给模型，形成闭环。

Observation：
Observation 是工具执行后的结果，比如检索到的门店列表、解析出的目标地点、规划出的路线。它不是直接展示给用户的最终答案，而是供后续推理使用的中间事实。

Working Memory：
Working memory 是运行时维护的临时工作记忆，用来保存这一轮会话里逐步积累的结构化事实，例如 `shops`、`route`、`destination`、`client_location`、`reply`。它相当于 ReAct 执行链路里的共享草稿区。

Loop Guard：
Loop guard 是 ReAct 系统常见的保护机制，用来限制最大步数，避免模型一直反复调用工具、迟迟不收敛。

Hub-and-Worker ReAct：
不是所有 ReAct 都只有一个 agent。在复杂一点的业务里，主 agent 可以先推理“该找谁做”，再把任务委派给 worker，worker 自己也跑一段 tool-augmented 推理，最后把结果返回给主 agent 总结。

Context Engineering：
ReAct 能否稳定执行，很大程度取决于上下文组织。好的运行时不会只把聊天历史原样丢给模型，而是会把 prompt、技能文档、运行时状态、最近工具结果、结构化上下文 payload 一起组装成更可读的输入。

在本项目中的应用：
Arcadegent 的 ReAct 不是把 “Thought / Action / Observation” 明文打印在用户界面里，而是把这套模式实现成一个运行时主循环。

整体流程是：

1. `ReactRuntime.run_chat()` 初始化 session，写入 `running` 状态，准备 working memory。
2. `_run_chat_session()` 记录用户 turn、推断意图、写入 `session.started` 事件。
3. `_run_main_agent()` 进入主循环：
   - 用 `ContextBuilder.build()` 组装 prompt、skills、runtime state、context payload
   - 调 `ProviderAdapter.complete()` 请求模型
   - 如果模型返回 tool calls，就进入 `_execute_tool_calls()`
   - 如果模型直接返回文本，就把它当作最终回复
4. `_execute_tool_calls()` 会先做参数补全和校验，再通过 `ToolRegistry.execute()` 执行工具。
5. 如果工具是 `invoke_worker`，运行时不会把它当普通工具结束，而是进一步进入 `_run_worker()`。
6. `_run_worker()` 会切换到 `search_worker` 或 `navigation_worker`，让 worker 也跑一个自己的 ReAct 循环，直到获得搜索结果或路线结果。
7. worker 产出的 artifacts 会被提升回主 session 的 working memory。
8. 主 agent 再继续基于这些 observation 决定是否继续调用工具，或者输出最终文本。
9. 最终回复会写入 `assistant.completed`，同时按 chunk 发出 `assistant.token` 事件供前端流式展示。

也就是说，这里的 ReAct 实现重点不在“把推理文本显式打印出来”，而在“模型驱动决策 + 运行时执行工具 + 结构化 observation 回写 + 循环直到收敛”。

### 参考回答

这个项目的 ReAct 是通过 `ReactRuntime` 的循环执行器实现的。主流程会先构造上下文，然后调用模型；如果模型返回的是 tool calls，运行时就去执行工具，把结果写入 working memory 和 turn history，再进入下一轮；如果模型返回的是最终文本，就结束循环。和经典 ReAct 不同的是，这里把 observation 主要做成结构化 artifacts，比如 `shops`、`route`、`destination`，而不是把所有中间推理都暴露成用户可见文本。

另外它还做了一个 hub-and-worker 变体。主 agent 遇到复杂检索或导航任务时，会通过 `invoke_worker` 把任务委派给 `search_worker` 或 `navigation_worker`。worker 自己也会跑一个受限工具集的循环，结果再回写给主 agent。最终的用户回复仍由主 agent 统一收口。

### 深度追问

它和“纯 prompt chaining”最本质的区别是什么？

### 深度追问回答

纯 prompt chaining 更像是工程代码提前写好固定流程，比如先调用 A，再调用 B，最后调用 C，模型主要负责填空。而这个项目的 ReAct 是把“下一步该做什么”的决策权交给模型：模型可以决定直接回答，或者调用 `db_query_tool`、`geo_resolve_tool`、`route_plan_tool`、`invoke_worker` 等工具，再根据 observation 继续推进。换句话说，链路不是完全写死的，运行时提供的是边界和保护，具体路径由模型在每一轮动态选择。

### 深度追问

模型发起 tool call 之后，结果是怎么回到下一轮上下文里的？

### 深度追问回答

有两条回流路径。第一条是 turn history：`_record_tool_result()` 会把工具结果记成 `role="tool"` 的 turn，这样后续上下文里能看到最近工具执行记录。第二条是 working memory：`_apply_tool_memory()` 会把关键结果写进结构化内存，比如 `shops`、`shop`、`route`、`destination`、`view_payload`。`ContextBuilder` 下一轮构建上下文时，会把这些内容压成 `runtime state` 和 `context_payload` 注入给模型，所以模型能够基于最新 observation 继续推理。

### 深度追问

为什么项目里没有把 Thought 明文输出出来，还是能叫 ReAct？

### 深度追问回答

因为 ReAct 的本质不是一定要把 “Thought: ... Action: ... Observation: ...” 这几个单词原样打印出来，而是推理和行动的交替机制。很多工程化系统为了安全性、稳定性和用户体验，不会把模型的原始 chain-of-thought 暴露给前端，而是只保留工具调用、状态变化和最终结果。Arcadegent 也是这个思路：保留 ReAct 的执行机制，但不把内部推理全文透出。

### 深度追问

主 agent 和 worker 的关系在 ReAct 里怎么理解？

### 深度追问回答

可以把它理解成分层 ReAct。主 agent 负责高层推理，判断当前需求是搜索、附近推荐还是导航，并决定是否要委派 worker。worker 负责更窄域的推理和工具调用，比如搜索 worker 只管检索机厅，导航 worker 只管目标解析和路线规划。这样做的好处是每个循环的 prompt 更聚焦，allowed tools 更窄，模型更不容易在复杂链路里跑偏。

### 深度追问

如果模型一直调用工具不收敛，系统怎么防止死循环？

### 深度追问回答

项目里用 `LoopGuard` 做硬限制。`_run_main_agent()` 和 `_run_worker()` 都会在循环前创建 `LoopGuard(self._max_steps)`，每轮先 `next()`，超过上限就抛出 `max_steps_reached`。此外，主流程里还会看 `working_memory` 是否已经有 `reply`，以及模型是否已经返回文本，一旦满足结束条件就会收口。也就是说，系统同时有“步数上限”和“结果就绪即停止”两层保护。

### 深度追问

这个 ReAct 运行时和 SSE 是怎么结合的？

### 深度追问回答

ReAct 负责产生过程事件，SSE 负责把这些过程事件实时推到前端。比如主流程启动时会发 `session.started`，切换 worker 时会发 `subagent.changed` 和 `worker.started`，工具执行时会发 `tool.started` / `tool.completed`，路线准备好时会发 `navigation.route_ready`，最终回复会发 `assistant.token` 和 `assistant.completed`。所以从用户视角看，前端看到的是一个持续更新的事件流；从后端视角看，本质上是 ReAct 循环每推进一步，就顺手往 replay buffer 里追加一个观测事件。

### 深度追问

为什么 `invoke_worker` 也被设计成工具，而不是在代码里直接 if-else 调 worker？

### 深度追问回答

把 worker dispatch 设计成工具，有两个好处。第一，主 agent 是通过统一的 tool-calling 机制决定“要不要委派”和“委派给谁”，这比在工程代码里硬编码分支更符合 ReAct 模式。第二，worker 调度也就自然纳入了统一的 schema 校验、权限控制、事件观测和 turn 记录体系。这样无论调用的是数据库工具、地图工具还是 worker，本质上都是同一种运行时动作，系统会更整齐。

### 源码定位

- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/runtime/loop_guard.py`
- `backend/app/agent/context/context_builder.py`
- `backend/app/agent/llm/provider_adapter.py`
- `backend/app/agent/tools/registry.py`
- `backend/app/agent/subagents/subagent_builder.py`
- `backend/app/agent/tools/builtin/executors/invoke_worker.py`
- `backend/app/agent/context/prompts/main_agent.md`


---

## 41. 补充高频问题：这个项目有没有记忆模块

### 可能问题

这个项目里有做 memory 吗，还是只是多轮对话 history？

### 相关知识点：概念及应用

Session-level Memory：
会话级记忆，指同一个 session 内持续保留的状态，包括用户消息、助手回复、工具执行记录和阶段性结果。

Turn History：
turn history 是按轮次保存的对话与工具记录。它偏“过程记忆”，让模型知道最近发生过什么。

Working Memory：
working memory 是运行时维护的结构化临时内存，用来保存这次任务执行过程中积累的关键事实，例如候选门店、选中的门店、路线、解析出的地点、知识检索命中和最近错误。

Session Persistence：
会话持久化指这些状态不只存在于一次函数调用里，而是会跟随 session 保存下来，支持续聊、恢复和结果回看。

Long-term Memory：
长期记忆通常指跨会话、跨时间的用户画像和偏好记忆，例如常驻城市、常玩机种、历史偏好路线方式等。

在本项目中的应用：
这个项目实现了会话级短期记忆，但没有完整意义上的长期记忆系统。也就是说，它不仅有聊天历史，还有结构化的 working memory 来支撑 ReAct 多步执行；但还没有做到跨很多会话自动沉淀和复用用户偏好。

### 参考回答

有，但这里的 memory 主要是工程化的会话级记忆，不是长期人格记忆。系统一方面会保留对话和工具调用的 turn history，另一方面会维护 working memory，把门店列表、地点解析结果、路线、知识检索命中这些结构化 observation 写进去。这样模型下一轮不只是看聊天文本，还能直接读取这次任务已经走到哪一步、拿到了哪些事实，所以它更适合支撑多轮搜索和导航这种业务型 Agent。

### 深度追问

那它算不算长期记忆？

### 深度追问回答

严格来说不算。它当前更像短期任务记忆和会话记忆，能支持一个 session 内的连续执行和恢复，但不会跨很多天自动记住用户偏好，也没有完整的用户画像总结、记忆检索和更新机制。所以比较稳的说法是：项目已经实现了会话级 memory，但还没有完整的长期 memory。

### 深度追问

如果以后要加长期记忆，你会怎么设计？

### 深度追问回答

我会把长期记忆和现在的 working memory 分层。working memory 继续负责“这一次任务做到哪一步”，长期记忆则负责“这个用户长期偏好什么”。实现上我不会把所有历史对话原样塞给模型，而是做记忆抽取，只保留高价值、相对稳定的事实，比如常驻城市、常玩机种、对路线方式的偏好。然后把长期记忆单独存储，按用户身份和当前问题做按需召回，再把相关片段注入新会话上下文。同时要支持更新、时间衰减和用户可删除，避免旧偏好长期污染回答。

### 源码定位

- `backend/app/agent/runtime/session_state.py`
- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/context/context_builder.py`
- `backend/app/api/http/chat.py`


---

## 42. 补充高频问题：这个项目里的 embedding 模型是什么

### 可能问题

你这个项目 RAG 用的 embedding 模型是什么？

### 相关知识点：概念及应用

Embedding Model：
embedding 模型负责把 query 和文档块编码成向量，供向量检索使用。

Fallback Embedding：
fallback embedding 是先保证系统可运行的回退方案，通常语义效果一般，但依赖少、接入轻。

Sentence-Transformers：
本地 Transformer embedding 的常见方案，适合在不依赖外部 API 的情况下做可控的本地语义检索。

Embedding API：
也可以把向量编码交给外部兼容接口服务，优点是接入快，缺点是可控性和部署独立性相对弱一些。

Reranker：
reranker 不是 embedding 模型，而是第二阶段的精排模型，负责对召回候选重新打分，和 embedding 的职责不同。

在本项目中的应用：
这个项目的 embedding 模型是可配置的。仓库默认示例配置更偏演示和跑通链路，使用内置的本地 fallback；如果需要更好的中文语义检索效果，也支持切到本地 `sentence-transformers` 模型，或者切到外部 embedding API。

### 参考回答

这个项目的 embedding 模型不是写死的，而是可配置的。默认示例配置用的是一个内置的本地 fallback，主要目的是先把 RAG 链路稳定跑通，不依赖额外向量服务。如果想做更真实的语义检索，可以切到本地 `sentence-transformers` 路线，比如中文常见的 BGE 系列模型；如果部署上更偏服务化，也可以切到外部 embedding API。所以面试里比较稳的说法是：这个项目已经把 embedding 抽象成可切换配置，不是只能绑定某一个模型。

### 深度追问

为什么不一开始就只用外部 embedding API？

### 深度追问回答

因为这个项目当前重点是先把 RAG 跑通并工程化，不是先把外部依赖堆满。内置 fallback 的好处是依赖少、启动门槛低、适合本地开发；切到本地 Transformer embedding 或外部 API 是后续的精度升级路径。这样做能把“链路跑通”和“检索精度优化”拆成两个阶段，工程上更稳。

### 深度追问

embedding 模型和 reranker 模型在这里怎么分工？

### 深度追问回答

embedding 负责第一阶段召回，也就是把 query 和知识块映射到同一个向量空间，快速找到相似候选。reranker 负责第二阶段精排，对召回出来的少量候选再做更精确的相关性判断。前者强调速度和覆盖面，后者强调精度。所以项目里就算 embedding 模型一般，只要 reranker 强，也可能改善排序；反过来，如果 embedding 召回不到相关候选，reranker 也救不回来。

### 源码定位

- `backend/app/rag/service.py`
- `backend/app/core/config.py`
- `backend/.env.example`
- `README.md`


---

## 43. 补充高频问题：Query 改写可以优化吗

### 可能问题

如果让你继续优化这个项目，你会不会做 query rewrite？当前 query 改写还有空间吗？

### 相关知识点：概念及应用

Query Rewrite：
query rewrite 指把用户原始问题改写成更适合检索的查询表达，目标是提升召回率、排序稳定性和意图解析准确率。

Slot Extraction：
slot extraction 指把一句自然语言拆成结构化字段，比如地区、门店名、机种名、排序意图、是否 nearby 等。

Synonym Normalization：
同义词归一化是把口语别称、缩写、圈内叫法映射到更稳定的标准词，例如机种别名、商圈简称和地区简称。

Fallback Query：
fallback query 指第一次检索失败后，不是机械重试，而是有策略地放宽条件、换检索通道或改用更合适的主题词。

Controlled Rewrite：
受控改写指改写结果有明确边界，例如只能输出结构化字段或有限的关键词，不让模型自由生成一大段不可控的新 query。

在本项目中的应用：
当前项目已经有一点弱改写能力，比如会从用户原话里抽取 `keyword`，也会通过 agent 决定走结构化检索还是知识检索，并在零结果时做一次 fallback。但它还没有独立、系统的 query rewrite 模块，所以这块是很值得继续优化的方向。

### 参考回答

我觉得可以，而且值得做。现在这个项目更多是“弱改写”，比如从用户原话里提取关键词、让 worker 决定该走结构化检索还是知识检索、零结果时做一次 fallback，但还没有显式的 query rewrite 层。对这个业务来说，用户原话里经常会混着地区、机种、门店名、排序意图和口语表达，所以如果能先做一层受控改写，把 query 拆成结构化字段，再决定检索策略，整体稳定性会更高。

### 深度追问

如果你真的做这块优化，会优先从哪里下手？

### 深度追问回答

我会先做规则型和结构化的 rewrite，而不是一上来就让大模型自由改写。第一步是槽位化抽取，把原句拆成地区、门店、机种、排序、nearby 意图这些字段；第二步是做领域同义词映射，比如机种别称、地区简称、常见口语；第三步才是在知识检索场景里做轻量语义改写，比如去掉礼貌语、保留核心主题词。这样更稳，也更容易 debug。

### 深度追问

为什么不直接让大模型自由把 query 重写一遍？

### 深度追问回答

因为自由改写虽然看起来聪明，但在这个场景里风险不小。它可能把用户原始约束改掉，比如把地区改错、把“最近”改成“推荐”、把门店问题改成泛化问题。这样一旦检索结果变差，很难判断是检索器的问题还是改写器的问题。所以我更倾向受控 rewrite：要么输出结构化字段，要么只输出有限关键词，而不是生成一大段新的自然语言 query。

### 深度追问

如果你只做一个最小优化，最推荐哪一步？

### 深度追问回答

我最推荐先做领域词表和结构化拆槽。因为这个项目是垂直领域，用户经常会用机种别称、圈内叫法和口语地区表达。只要先把这些词标准化，再把 query 拆成更清晰的参数，往往就能比单纯换模型更快见效，而且工程代价相对小。

### 源码定位

- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/context/prompts/search_worker.md`
- `backend/app/agent/tools/builtin/executors/db_query.py`
- `backend/app/agent/tools/builtin/executors/knowledge_search.py`
- `backend/app/infra/db/local_store.py`


---

## 44. 补充高频问题：LoRA 可以在这个项目里应用吗

### 可能问题

如果面试官问你 LoRA 能不能用在这个项目里，你怎么回答？

### 相关知识点：概念及应用

LoRA：
LoRA 是低秩适配微调方案，核心思想是在不全量更新大模型参数的前提下，用更小的可训练增量参数完成领域适配。

QLoRA：
QLoRA 是 LoRA 的低比特量化训练变体，更适合显存资源有限的场景。

Chat Model Adaptation：
把 LoRA 应用于主聊天模型，通常更适合提升输出风格、任务格式稳定性和指令跟随习惯。

Embedding / Reranker Adaptation：
把 LoRA 应用于 embedding 或 reranker，更适合提升垂直领域检索质量和相关性排序。

Serving vs Training：
能接入 LoRA 模型，不等于仓库本身就是 LoRA 训练工程。一个项目可能只负责调用已经部署好的 LoRA 模型，而不负责训练流程。

在本项目中的应用：
这个项目当前主线是 OpenAI-compatible LLM + RAG + 工具调用，不是原生的微调训练框架。所以 LoRA 不是完全不能用，而是更适合以“外部已部署模型接入”或“RAG 侧模型适配”的方式接入，而不是直接把仓库改造成训练工程。

### 参考回答

可以用，但要分场景说。这个项目最顺的接法不是把它改造成 LoRA 训练框架，而是把已经做过 LoRA 适配的模型作为外部可调用模型接进来，或者把 LoRA 用在 RAG 的 embedding / reranker 这一层。因为项目当前的主链路是模型调用、工具编排和检索增强，不是训练栈。如果目标是提升回复风格和格式稳定性，LoRA 更适合主聊天模型；如果目标是提升垂直领域的召回和排序，LoRA 更适合用在 embedding 或 reranker。

### 深度追问

如果三条路都能做，你最推荐哪条？

### 深度追问回答

如果只看这个项目的当前形态，我最推荐优先做检索侧，也就是把 LoRA 相关探索放到 embedding 或 reranker 上，或者先做 query rewrite 这类更低成本的检索优化。因为这个项目很多问题本质上不是“模型不会说”，而是“能不能先找对信息”。如果信息找准了，主聊天模型哪怕不微调，整体回答也会提升很多。

### 深度追问

那什么时候更适合把 LoRA 放到主聊天模型上？

### 深度追问回答

当你的目标更偏输出风格、任务格式和回答一致性时，主聊天模型上的 LoRA 价值会更大。比如你希望回答结构非常固定、措辞风格稳定、工具调用前后的总结口径更统一，这类需求通常更适合聊天模型适配，而不是检索侧适配。

### 深度追问

为什么你不建议一开始就把这个仓库改成 LoRA 训练工程？

### 深度追问回答

因为当前仓库更像应用编排工程，而不是训练基础设施。它已经比较完整地解决了上下文构建、工具调用、RAG、SSE 和会话状态这些应用层问题。要补成训练工程，需要额外加数据清洗、标注格式、训练脚本、评估集、模型管理和部署流程，成本和风险都更高。对这个项目来说，更现实的路线通常是先把 LoRA 当成外部能力接进来，再评估是否值得把训练链路也纳入仓库。

### 源码定位

- `backend/app/infra/llm/openai_compatible_client.py`
- `backend/app/agent/llm/provider_adapter.py`
- `backend/app/rag/service.py`
- `backend/pyproject.toml`
- `README.md`


---

## RAG检索优化部分

RAG检索优化相关的面试题已独立整理，包含：

- **问题26**: RAG检索系统的重排序机制
- **问题27**: RAG混合检索（Hybrid Search）
- **问题28**: RAG评估体系

详见：[interview-question-bank-rag-supplement.md](./interview-question-bank-rag-supplement.md)

### RAG优化核心要点速记

**重排序（Reranker）**
- 两阶段检索：向量召回 + Cross-encoder精排
- 预期提升10-20% Top-1准确率
- 三种实现：SentenceTransformer、Keyword、Base
- 自动降级机制保证稳定性

**混合检索（Hybrid Search）**
- 结合向量检索和BM25关键词检索
- 得分融合：final_score = alpha × vector + (1-alpha) × bm25
- 自实现BM25算法，支持中英文分词
- 通过alpha参数调节权重（0.0-1.0）

**评估体系**
- 三个核心指标：Top-1准确率、Hit@K准确率、片段匹配率
- 27个测试用例覆盖商家评论、FAQ、指南三类场景
- 参数扫描实验找到最优配置
- 完整的评估脚本支持A/B测试

---

**文档版本**：v1.2（新增记忆、embedding、query rewrite、LoRA面试问答）  
**最后更新**：2026年7月
