# Arcadegent 小白入门拆解

这份文档不是写给熟手程序员的。

它是写给下面这种情况的人看的：

- 刚开始学编程
- 看代码容易晕
- 看到 `Agent`、`MCP`、`SSE` 这种词会紧张
- 想把这个项目真正看懂，慢慢讲成“我自己的项目”

如果你现在就是这种状态，不用着急。这个项目虽然文件不少，但核心思路其实没有那么玄。

你只需要先记住一句话：

`Arcadegent` 是一个“帮用户找音游机厅、推荐附近门店、规划路线”的全栈项目。

它的本质可以拆成 4 个部分：

1. 前端页面：负责让用户输入问题、看结果、看地图。
2. 后端接口：负责接收请求、查数据、启动 Agent。
3. 数据层：负责存机厅信息，支持搜索、筛选、排序。
4. Agent 层：负责理解用户意图，决定“查店”还是“规划路线”。

---

## 1. 先不要看代码，先看“它是干嘛的”

项目根说明在 `README.md`。

从 `README.md` 可以先得到 3 个最重要的结论：

1. 这是一个“音游机厅检索 + Agent 问答 + 路线建议”的项目。
2. 技术上是前后端分离：
   - 前端在 `apps/web`
   - 后端在 `backend`
3. 它不是纯聊天机器人，而是“聊天 + 数据查询 + 地图导航”的组合型应用。

换句话说，这个项目不是让模型随便聊天，而是让模型带着工具做事。

你可以把它理解成：

“用户在前端提问，后端的 Agent 判断该怎么做，再调用查店工具、地理工具、路线工具，最后把结果以文字和地图一起返回。”

---

## 2. 用一句最简单的话理解整体架构

先别背术语，先看人话版本：

1. 用户在网页里输入一句话，比如“帮我找上海附近的 maimai 机厅”。
2. 前端把这句话发给后端。
3. 后端的 Agent 判断用户是在“搜索机厅”还是“导航去机厅”。
4. Agent 决定调用哪些工具：
   - 查数据库
   - 查地理位置
   - 算路线
5. 后端把处理过程通过 SSE 实时推给前端。
6. 前端一边显示回答文字，一边显示地图、门店、路线。

如果你能把上面 6 句话讲顺，这个项目你就已经入门了。

---

## 3. 目录怎么读，才不会迷路

建议你只先盯住下面这些目录：

```text
apps/web/                     前端 React 页面
backend/app/                  后端 FastAPI 主体
backend/app/agent/            Agent 编排逻辑
backend/app/api/              HTTP 和 SSE 接口
backend/app/infra/db/         数据读取
backend/app/services/         地理、数据映射等服务
docs/                         项目文档
```

你可以把这个仓库理解成两栋楼：

- `apps/web/`：给用户看的楼
- `backend/app/`：真正处理业务的楼

而 `backend/app/agent/` 是这栋后端大楼里最“聪明”的那个办公室。

---

## 4. 第一步看后端入口：应用是怎么启动的

最值得先看的文件是：

- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/container.py`
- `backend/app/core/lifecycle.py`

### 4.1 `backend/app/main.py` 在做什么

这个文件是后端入口。

它做了 5 件事：

1. 读取配置
2. 初始化日志
3. 构建依赖容器
4. 注册路由
5. 配置应用启动和关闭时要做的事情

你可以把它理解成“后端总装厂”。

### 4.2 `backend/app/core/config.py` 在做什么

这个文件专门负责读取环境变量，也就是项目运行配置。

比如它会读这些内容：

- 端口是多少
- 数据源是 `jsonl` 还是 `supabase`
- LLM 的 API 地址和模型名
- 高德地图 API Key
- MCP 服务器配置目录

你可以把它理解成：

“项目运行前先读设置表，决定去哪里拿数据、连哪个模型、用哪些服务。”

### 4.3 `backend/app/core/container.py` 在做什么

这个文件非常关键。

它把项目里要长期使用的对象全部组装起来，比如：

- 数据仓库 `store`
- 会话存储 `session_store`
- 地理解析器 `arcade_geo_resolver`
- 工具注册表 `tool_registry`
- Agent 运行时 `react_runtime`
- 总调度器 `orchestrator`

你可以把它理解成：

“把整个项目要用的零件组装成一台机器。”

### 4.4 `backend/app/core/lifecycle.py` 在做什么

应用启动时，它会做两件事：

1. 检查数据源健康状态
2. 刷新工具列表

所以后端启动后，项目不仅要“能跑起来”，还要确认“数据和工具是否准备好”。

---

## 5. 第二步看接口层：前端到底调用了哪些接口

先看这些文件：

- `backend/app/api/http/arcades.py`
- `backend/app/api/http/chat.py`
- `backend/app/api/http/regions.py`
- `backend/app/api/http/location.py`
- `backend/app/api/http/health.py`
- `backend/app/api/stream/sse.py`

### 5.1 `/api/arcades`

这个接口负责“查机厅列表”和“查门店详情”。

它支持：

- 关键词搜索
- 省市区筛选
- 只看有机台的门店
- 按更新时间、机台数、距离排序
- 分页

这说明这个项目不是只靠 LLM，它本身先是一个“可用的数据查询系统”。

### 5.2 `/api/chat`

这个接口负责“同步聊天”。

也就是说，用户发一句话，后端等整个处理结束后再一次性返回结果。

不过这个项目更常用的是另一个接口：

- `/api/chat/sessions`

它会先把聊天任务丢到后台执行，然后立刻返回一个 `session_id`。

为什么要这样做？

因为 Agent 处理不是一瞬间完成的，它可能会：

1. 判断意图
2. 调用工具
3. 查门店
4. 查路线
5. 最后再总结回答

所以更合理的方式是“异步会话 + 流式更新”。

### 5.3 `/api/stream/{session_id}`

这个接口非常重要。

它使用的是 `SSE`，也就是服务器持续把事件推给前端。

推送的事件包括：

- `session.started`
- `subagent.changed`
- `tool.started`
- `assistant.token`
- `assistant.completed`
- `session.failed`

你可以把它理解成：

“前端不是傻等后端处理完，而是一边等，一边实时看后端现在进行到哪一步了。”

### 5.4 `/api/regions`

这个接口给前端的地区筛选使用。

比如：

- 拉省份列表
- 选了省后拉城市列表
- 选了城市后拉区县列表

这是典型的后台支撑型接口。

### 5.5 `/api/location/reverse-geocode`

这个接口负责逆地理编码。

说简单点：

前端拿到经纬度后，后端把它翻译成“这是哪个城市、哪个区”。

这样 Agent 在回答“附近有什么机厅”时就更有上下文。

### 5.6 `/health`

这个接口不是给普通用户看的，更多是给开发和部署时排查问题用的。

它会告诉你：

- 服务活着没
- 数据源正常没
- 工具系统正常没
- MCP 工具发现成功没

---

## 6. 第三步看数据层：机厅数据是怎么被查出来的

先看：

- `backend/app/infra/db/local_store.py`
- `backend/app/infra/db/supabase_repository.py`
- `backend/app/core/container.py`

### 6.1 数据源有两种模式

项目支持两种数据源：

1. `jsonl`
2. `supabase`

默认是 `jsonl`。

这意味着项目在开发时，可以直接读本地文件，不一定非要连数据库。

这对个人项目很友好，因为：

- 本地更容易跑起来
- 成本更低
- 排查更直观

### 6.2 `local_store.py` 的核心作用

这个文件可以看成一个“本地轻量数据库”。

它做的事情包括：

- 读取 JSONL 文件
- 规范化字段
- 生成搜索用文本
- 按关键词筛选
- 按地区筛选
- 按机种筛选
- 按距离排序

其中最值得你记住的一点是：

它不是“把数据读进来就完事”，而是自己实现了一套查询逻辑。

这代表作者没有把项目做成“死数据展示”，而是做成了“有查询能力的数据服务”。

### 6.3 这层的本质是什么

本质上就是一句话：

“把原始机厅数据，变成后端可以快速查询的结构化数据。”

---

## 7. 第四步看 Agent：项目最核心也最容易让人怕的部分

先看这些文件：

- `backend/app/agent/runtime/orchestrator.py`
- `backend/app/agent/runtime/react_runtime.py`
- `backend/app/agent/context/context_builder.py`
- `backend/app/agent/subagents/subagent_builder.py`
- `backend/app/agent/nodes/definitions/*.yaml`

先别怕，Agent 没你想的那么玄。

这个项目里的 Agent，本质是：

“一个会调用工具、会分工、会根据上下文组织回答的任务执行器。”

### 7.1 `orchestrator.py` 在做什么

这个文件像总调度器。

它解决两个问题：

1. 给会话分配 `session_id`
2. 防止同一个会话被重复并发执行

所以它像一个“会话管理员”。

### 7.2 `react_runtime.py` 在做什么

这个文件是整个 Agent 的心脏。

它负责：

1. 准备会话状态
2. 推断用户意图
3. 记录对话历史
4. 构建 Prompt 上下文
5. 调用模型
6. 执行模型请求的工具
7. 保存工具结果到 working memory
8. 把结果通过 SSE 持续推给前端
9. 生成最终回答

如果只记一句话，可以记：

`react_runtime.py` = “Agent 真正干活的地方”

### 7.3 这个项目里的 Agent 不是单兵，而是分角色的

`subagent_builder.py` 里定义了 3 个主要角色：

1. `main_agent`
2. `search_worker`
3. `navigation_worker`

你可以把它们理解成公司里的 3 个人：

- `main_agent`：项目经理，负责理解问题、分派任务、汇总结果
- `search_worker`：查资料的人，负责查门店和筛选结果
- `navigation_worker`：路线规划的人，负责算怎么去

### 7.4 为什么这里要拆 worker

因为一个模型如果同时负责：

- 理解用户问题
- 查店
- 查路线
- 总结成自然语言

就容易混乱。

拆成 worker 的好处是：

- 职责清晰
- 工具权限更容易控制
- Prompt 更好管理
- 后续扩展更方便

### 7.5 `context_builder.py` 为什么重要

很多小白会觉得 Prompt 就是一段系统提示词。

其实在这个项目里，Prompt 不是一段固定文字，而是“动态拼出来的上下文包”。

`context_builder.py` 会把这些内容组合给模型：

- 系统提示
- 当前子 Agent 提示
- 技能片段
- 用户位置
- 当前会话状态
- 最近对话历史
- 最近工具结果
- 当前 working memory

所以你可以这样理解：

“模型不是凭空回答，它是在读完整个任务上下文后再决定下一步。”

---

## 8. 第五步看工具系统：模型不是直接查数据，而是通过工具做事

先看：

- `backend/app/agent/tools/registry.py`
- `backend/app/agent/tools/builtin/provider.py`
- `backend/app/agent/tools/builtin/tools_manifest.json`
- `backend/app/agent/tools/builtin/executors/`
- `backend/app/agent/tools/mcp/`

### 8.1 为什么需要工具系统

LLM 自己不会直接访问数据库，也不会直接知道机厅列表。

所以需要给它“手和脚”。

这些“手和脚”就是工具。

### 8.2 这个项目有哪些内建工具

从 `tools_manifest.json` 可以看到，主要内建工具有：

- `invoke_worker`
- `db_query_tool`
- `geo_resolve_tool`
- `route_plan_tool`
- `summary_tool`

你可以把它们理解成：

- `invoke_worker`：叫另一个 worker 来帮忙
- `db_query_tool`：查机厅数据
- `geo_resolve_tool`：处理地点信息
- `route_plan_tool`：算路线
- `summary_tool`：把结果整理成人话

### 8.3 `registry.py` 在做什么

它是工具系统的统一入口。

它负责：

1. 收集所有工具
2. 校验工具参数
3. 检查权限
4. 把执行请求分发给正确的工具提供者

这就像一个“工具总台”。

### 8.4 `builtin/provider.py` 为什么值得记

这个文件说明项目不是把工具硬编码写死的。

它用了 `manifest + schema + executor` 的设计。

也就是说，一个工具通常拆成三部分：

1. 工具定义
2. 参数 Schema
3. 执行逻辑

这是一个很像正式工程的设计，优点是：

- 方便扩展新工具
- 参数更规范
- 测试更好写
- 工具定义更清晰

### 8.5 MCP 是什么，为什么这里会出现

你现在不用把 `MCP` 理解得特别深。

在这个项目里，你只要先把它理解成：

“一种把外部工具接进来的标准方式。”

这个项目会在启动时扫描 `backend/app/agent/tools/mcp/servers/*.json`，
发现远程可用工具后，把它们映射成本地工具名，比如：

- `mcp__amap__maps_direction_walking`

这说明项目不只会用自己写的工具，还会动态接第三方工具。

这在面试里是一个加分点，因为它体现了扩展性。

---

## 9. 第六步看前端：用户看见的页面是怎么工作的

先看这些文件：

- `apps/web/src/App.tsx`
- `apps/web/src/hooks/useChatSessionController.ts`
- `apps/web/src/hooks/useStreamReply.ts`
- `apps/web/src/stores/appStore.ts`
- `apps/web/src/stores/arcadeBrowserStore.ts`
- `apps/web/src/api/client.ts`

### 9.1 `App.tsx` 并不复杂

`App.tsx` 的工作很直接：

- 左边是侧边栏
- 上面是顶部栏
- 中间根据模式切换：
  - 聊天页 `ChatPanel`
  - 机厅浏览页 `ArcadeBrowser`

所以它更像“总页面壳子”。

### 9.2 前端最重要的文件其实是 `useChatSessionController.ts`

这个 Hook 基本上是聊天功能总控台。

它负责：

- 加载历史会话
- 选择会话
- 发起聊天
- 建立 SSE 连接
- 接收流式事件
- 更新界面状态
- 删除会话

如果后端的总调度器是 `orchestrator`，
那么前端的总调度器就是 `useChatSessionController.ts`。

### 9.3 为什么前端要用 Zustand

`appStore.ts` 和 `arcadeBrowserStore.ts` 是状态仓库。

它们负责保存：

- 当前页面模式
- 当前会话 ID
- 对话内容
- 流式状态
- 当前激活的 subagent
- 地图数据
- 机厅列表筛选状态

这样做的好处是：

- 页面组件不用互相传很长的 props
- 状态集中
- 逻辑更清楚

### 9.4 `useStreamReply.ts` 的作用

这个文件专门处理“流式回复显示效果”。

它不是等完整文本回来再一起显示，而是：

1. 接收 token 或完整文本
2. 缓存在队列里
3. 按一定节奏一点点刷到页面上

这样用户会感觉回答是“活的”，不是一下子跳出来的。

### 9.5 `api/client.ts` 是什么

这个文件是前端请求后端的统一封装。

好处是：

- URL 构造集中管理
- 错误处理集中管理
- 页面组件不用自己手写很多 `fetch`

---

## 10. 用一条完整链路理解项目：用户发一句话后发生了什么

下面这段是你最应该反复看的。

假设用户说：

`帮我找上海附近的 maimai 机厅`

系统内部大致按这个顺序工作：

1. 前端 `ChatPanel` 触发提交。
2. `useChatSessionController.ts` 生成或复用 `session_id`。
3. 前端调用 `/api/chat/sessions` 发起异步会话。
4. 后端 `chat.py` 把请求交给 `orchestrator`。
5. `orchestrator.py` 检查这个会话是否正在运行。
6. `react_runtime.py` 初始化会话状态和 working memory。
7. Agent 根据消息判断意图，大概率是 `search_nearby`。
8. `main_agent` 构建上下文并调用模型。
9. 模型决定要调用 `invoke_worker`，派 `search_worker` 去查数据。
10. `search_worker` 调 `db_query_tool`。
11. `db_query_tool` 到 `local_store.py` 或 Supabase 查询机厅。
12. 查询结果回到 working memory。
13. 如果需要路线，Agent 会继续调用 `route_plan_tool` 或 MCP 路线工具。
14. 后端在执行过程中不断往 SSE 推送事件。
15. 前端 EventSource 持续收到事件，更新进度、文字、地图。
16. 最终回答生成后，后端推送 `assistant.completed`。
17. 前端停止流连接，刷新会话详情，展示最终结果。

你如果能把这 17 步顺下来，已经比很多“只会背技术栈”的人更接近真正理解项目了。

---

## 11. 这个项目的亮点，应该怎么讲

如果你以后要介绍这个项目，不要只说：

“这是一个 React + FastAPI + Agent 项目。”

这种说法太空。

更好的讲法是：

### 11.1 产品层亮点

- 它不是纯聊天，而是把“搜索 + 推荐 + 导航”整合在一个体验里。
- 用户既能问问题，也能直接看地图和路线。

### 11.2 工程层亮点

- 前后端分离，职责比较清楚。
- 聊天采用异步会话 + SSE 流式回传，交互体验更好。
- 工具系统做了统一注册和参数校验，扩展性不错。
- Agent 采用主 Agent + worker 的分工式架构，不是简单单轮问答。

### 11.3 数据层亮点

- 支持本地 JSONL 和 Supabase 两种数据源。
- 本地数据读取层自己实现了搜索、筛选、排序和距离计算。

### 11.4 地图能力亮点

- 不只是展示地图，还包含定位、逆地理编码、路线规划。
- 同时兼容内建路线工具和 MCP 外部工具。

---

## 12. 你怎么把它“变成自己的项目”

这里我会说得很直接。

“变成自己的项目”不应该理解成“假装全部都是自己从零写的”。

更好的做法是：

把它真正理解到你能讲、能跑、能改、能演示。

这样它就会慢慢变成你的项目经验。

### 12.1 现在你能诚实地怎么说

如果你目前主要是在学习和拆解这个项目，你可以这样说：

“我系统地拆解并复现了一个机厅检索与导航 Agent 项目，完成了本地运行、架构梳理、核心链路理解，并整理了项目分析文档。现在我可以独立讲清它的前后端结构、Agent 编排、工具调用和流式交互流程。”

这句话是成立的，而且不虚。

### 12.2 如果你后续做了二次开发，可以怎么说

当你真的做了修改，比如：

- 改界面
- 新增接口
- 优化筛选
- 新增地图功能
- 替换模型或工具
- 增加日志和测试

你就可以说：

“我基于 Arcadegent 做了二次开发，负责理解并改造其前端会话流、后端 Agent 工具链路和数据检索能力。”

这时候“属于你”的程度就更高了。

### 12.3 面试时最安全的表达方式

建议你用下面这种说法：

“这是我深入拆解并完成本地复现的项目，我重点理解和实践的是它的 Agent 编排、工具系统、流式会话和地图链路。对于原项目中我没有亲自从零实现的部分，我能讲清设计思路和实际运行流程；对于我后续修改过的部分，我可以讲具体实现细节。”

这比“全是我写的”更稳，也更容易赢得信任。

---

## 13. 如果你要把它讲成自己的项目，可以这样背

下面这段是一个适合小白的“项目介绍模板”，你可以慢慢改成自己的话。

### 13.1 30 秒版本

“我做过一个叫 Arcadegent 的全栈项目，主要解决音游玩家找机厅、看附近门店和规划路线的问题。前端用 React 做聊天和地图展示，后端用 FastAPI 提供数据接口和会话接口，中间接了一个 Agent 层，用来识别用户意图、调用查店和路线工具，再把结果通过 SSE 流式返回给前端。”

### 13.2 1 分钟版本

“这个项目的特点不是单纯聊天，而是把机厅搜索、附近推荐和路线规划整合成一个 Agent 应用。后端会先根据用户输入判断意图，再由主 Agent 把任务分给搜索 worker 或导航 worker。工具层支持数据库查询、地理解析、路线规划和总结回复，外部地图能力还能通过 MCP 动态接入。前端则通过 Zustand 管状态，用 SSE 实时接收后端事件，所以用户能看到回答和地图过程是同步更新的。”

### 13.3 如果别人继续追问“你最理解哪一块”

你可以答：

“我目前最理解的是整条请求链路：前端发起会话、后端创建 session、Agent 调工具、SSE 回传、前端更新状态和地图展示。因为我就是沿着这条链路把项目拆开的。”

---

## 14. 建议你按这个顺序继续读代码

如果你一次看太多会崩，建议严格按这个顺序：

1. `README.md`
2. `backend/app/main.py`
3. `backend/app/core/config.py`
4. `backend/app/core/container.py`
5. `backend/app/api/http/chat.py`
6. `backend/app/api/stream/sse.py`
7. `backend/app/agent/runtime/orchestrator.py`
8. `backend/app/agent/runtime/react_runtime.py`
9. `backend/app/agent/tools/registry.py`
10. `backend/app/infra/db/local_store.py`
11. `apps/web/src/App.tsx`
12. `apps/web/src/hooks/useChatSessionController.ts`
13. `apps/web/src/stores/appStore.ts`
14. `apps/web/src/api/client.ts`

读的时候每个文件只回答 3 个问题：

1. 它的职责是什么？
2. 它接收谁的数据？
3. 它把结果交给谁？

你不要一开始就追求“每一行代码都懂”。

先懂“这个文件在整个链路里扮演什么角色”，更重要。

---

## 15. 你现在最需要记住的关键词

下面这些词，你不用一次全会，但要能说出大概意思：

- `FastAPI`：后端 Web 框架
- `React`：前端页面框架
- `Zustand`：前端状态管理
- `SSE`：服务端持续推送事件给前端
- `Session`：一次聊天会话
- `Agent`：会决定下一步怎么做的智能执行层
- `Worker`：被分派具体任务的子角色
- `Tool`：给模型调用的功能能力
- `MCP`：接入外部工具的一种标准方式
- `JSONL`：一行一条 JSON 的数据文件格式
- `Working Memory`：Agent 在当前会话里的临时记忆

---

## 16. 你下一步最值得做的 4 件事

如果你真的想把它逐渐变成自己的项目，最建议你做这 4 件事：

1. 自己把项目跑起来，哪怕先只跑后端。
2. 自己画一张“用户一句话 -> 后端 -> Agent -> 工具 -> 前端”的流程图。
3. 自己口头讲一遍第 10 节的完整链路。
4. 选一个很小的改动亲手做，比如改一个筛选项、改一个提示词、加一个接口字段。

只要你亲手改过哪怕一个点，这个项目就会从“看过”变成“做过”。

---

## 17. 最后给你的判断标准

什么时候算你真的开始理解这个项目了？

不是你能背出多少技术名词。

而是你能不能不用看代码，讲清下面这 5 句话：

1. 这个项目解决什么问题。
2. 前端和后端分别做什么。
3. Agent 为什么存在。
4. 工具系统为什么存在。
5. 用户发一句话后，系统内部发生了什么。

如果这 5 句话你能用自己的话说出来，这个项目就已经开始属于你了。
