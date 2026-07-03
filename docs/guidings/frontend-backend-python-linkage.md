# Arcadegent 前端、后端与 Python 联动说明

这份文档专门回答一个问题：

**这个项目里，前端、后端和 Python 到底是怎么联动起来的？**

如果你现在对“前端发请求、后端接请求、Python 处理业务”这套关系还是模糊的，这份文档就是写给你的。
可以，压缩成你面试时更好讲的版本如下。
30 秒版本
这个项目是一个面向音游玩家的机厅搜索和导航系统。前端用 React 负责聊天界面、机厅列表和地图展示；后端用 FastAPI 提供查询接口、会话接口和 SSE 流式接口；Python 负责真正的业务逻辑，包括机厅数据查询、Agent 编排、工具调用和路线规划。整体链路就是前端发请求，后端用 Python 处理，再把结果和执行过程实时推回前端。
1 分钟版本
这个项目本质上是一个“前端展示 + Python 后端处理 + Agent 工具调度”的全栈应用。前端用 React 和 Zustand 管理聊天状态、历史会话、地图和机厅筛选，用户输入问题后，前端会先调用 FastAPI 的会话接口，再通过 SSE 持续接收后端返回的执行过程。后端这边用 Python 实现了数据层、Agent Runtime 和工具系统，能够根据用户问题判断是查机厅、查附近还是规划路线，再调用 db_query_tool、地理解析和路线工具，把结果写入会话状态，最后返回文字回复、门店列表和地图路线。简单说，前端负责交互，后端负责调度，Python 负责把查询、Agent 和地图能力串起来。
最适合背的一句
前端负责发请求和展示，FastAPI 负责接请求和推事件，Python 负责查数据、跑 Agent、调工具，再把结果实时返回给前端。
如果你要，我还可以继续帮你压成两版：
---

## 1. 先用一句最简单的话理解

这个项目的联动关系可以先压缩成一句话：

**前端负责收集用户操作并展示结果，Python 后端负责接收请求、运行业务逻辑、调用 Agent 和工具，再把结果通过 JSON 或 SSE 返回给前端。**

你可以把它理解成下面这个流程：

```text
用户操作页面
  -> 前端 React 发请求
  -> 后端 FastAPI 接口接单
  -> Python 代码处理数据 / 跑 Agent / 调工具
  -> 后端返回 JSON 或 SSE 事件流
  -> 前端更新文字、地图、会话状态
```

如果只记住这 5 行，你就已经抓住主干了。

---

## 2. 三者分别是什么角色

### 2.1 前端是什么

前端在这个项目里主要是 `React + TypeScript`，代码在 `apps/web/` 下面。

前端负责的事情包括：

- 展示聊天界面和机厅浏览界面
- 接收用户输入
- 调用后端 API
- 接收流式事件
- 更新页面上的文字、进度、地图、门店信息

核心入口和关键文件：

- [apps/web/src/main.tsx](/Users/zw/Arcadegent/apps/web/src/main.tsx:1)
- [apps/web/src/App.tsx](/Users/zw/Arcadegent/apps/web/src/App.tsx:1)
- [apps/web/src/api/client.ts](/Users/zw/Arcadegent/apps/web/src/api/client.ts:1)
- [apps/web/src/hooks/useChatSessionController.ts](/Users/zw/Arcadegent/apps/web/src/hooks/useChatSessionController.ts:1)
- [apps/web/src/stores/appStore.ts](/Users/zw/Arcadegent/apps/web/src/stores/appStore.ts:1)

你可以把前端理解成：

**“用户和系统之间的可视化中间层。”**

---

### 2.2 后端是什么

后端在这个项目里主要是 `FastAPI`，代码在 `backend/app/` 下面。

后端负责的事情包括：

- 提供 HTTP API
- 提供 SSE 流式接口
- 管理会话状态
- 调用 Agent Runtime
- 调用数据层和地图服务
- 返回统一格式的数据

后端入口和关键文件：

- [backend/app/main.py](/Users/zw/Arcadegent/backend/app/main.py:1)
- [backend/app/api/http/chat.py](/Users/zw/Arcadegent/backend/app/api/http/chat.py:1)
- [backend/app/api/http/arcades.py](/Users/zw/Arcadegent/backend/app/api/http/arcades.py:1)
- [backend/app/api/stream/sse.py](/Users/zw/Arcadegent/backend/app/api/stream/sse.py:1)
- [backend/app/core/container.py](/Users/zw/Arcadegent/backend/app/core/container.py:1)

你可以把后端理解成：

**“系统的大脑入口和业务分发中心。”**

---

### 2.3 Python 在这个项目里是什么

很多初学者会把“后端”和“Python”混成一件事。

这里要分清：

- `FastAPI` 是后端框架
- `Python` 是这个后端以及大量业务逻辑所使用的语言

也就是说，Python 不只是“启动一个后端服务”，它还承担了很多真正的业务处理工作，比如：

- 读取和筛选机厅数据
- 组织 Agent 上下文
- 编排多角色 Agent
- 执行工具调用
- 处理地图和坐标相关逻辑
- 保存会话状态和事件

关键 Python 业务模块：

- [backend/app/infra/db/local_store.py](/Users/zw/Arcadegent/backend/app/infra/db/local_store.py:1)
- [backend/app/agent/runtime/react_runtime.py](/Users/zw/Arcadegent/backend/app/agent/runtime/react_runtime.py:1)
- [backend/app/agent/runtime/orchestrator.py](/Users/zw/Arcadegent/backend/app/agent/runtime/orchestrator.py:1)
- [backend/app/agent/tools/registry.py](/Users/zw/Arcadegent/backend/app/agent/tools/registry.py:1)
- [backend/app/services/](/Users/zw/Arcadegent/backend/app/services)

所以更准确地说：

**这个项目是“React 前端 + FastAPI 后端 + Python 业务逻辑”的联动系统。**

---

## 3. 项目启动时三者是怎么接上的

先从“项目启动”开始理解，会更稳。

### 3.1 前端启动

前端从 [apps/web/src/main.tsx](/Users/zw/Arcadegent/apps/web/src/main.tsx:1) 启动。

它会做两件事：

1. 挂载 React 应用
2. 注册 Service Worker

然后 [apps/web/src/App.tsx](/Users/zw/Arcadegent/apps/web/src/App.tsx:1) 负责渲染整体页面壳子。

页面里主要分两种视图：

- `chat`
- `arcades`

也就是：

- 聊天视图
- 机厅浏览视图

---

### 3.2 后端启动

后端从 [backend/app/main.py](/Users/zw/Arcadegent/backend/app/main.py:1) 启动。

后端启动时会：

1. 读取环境变量配置
2. 初始化日志
3. 构建依赖容器
4. 注册接口路由
5. 启动生命周期钩子

其中依赖容器在 [backend/app/core/container.py](/Users/zw/Arcadegent/backend/app/core/container.py:1) 里构建。

容器会提前把很多核心对象装配好，比如：

- `store`
- `session_store`
- `tool_registry`
- `react_runtime`
- `orchestrator`
- `arcade_geo_resolver`

这一步很重要，因为它决定了后面接口处理请求时可以直接拿哪些能力来用。

---

### 3.3 Python 业务对象在启动时就被装配好了

这个项目不是每来一个请求才临时创建全部对象。

很多核心能力在启动阶段就已经准备好了，比如：

- 数据仓库
- 工具注册表
- Agent Runtime
- 地理服务
- 会话存储

这样做的好处是：

- 请求处理更稳定
- 模块职责更清楚
- 各层之间更容易复用

---

## 4. 前端和后端靠什么通信

这个项目里，前后端主要通过两种方式通信：

1. `HTTP + JSON`
2. `SSE`

---

### 4.1 HTTP + JSON

这是最常见的通信方式。

前端会通过 `fetch` 调用后端接口，后端返回 JSON。

前端统一请求封装在：

- [apps/web/src/api/client.ts](/Users/zw/Arcadegent/apps/web/src/api/client.ts:1)

这里封装了很多接口调用函数，比如：

- `listArcades`
- `getArcadeDetail`
- `listProvinces`
- `listCities`
- `listCounties`
- `sendChat`
- `dispatchChatSession`
- `getChatSession`
- `listChatSessions`
- `deleteChatSession`
- `reverseGeocodeLocation`

这些函数本质上就是：

**把前端的函数调用，翻译成对后端 URL 的 HTTP 请求。**

比如：

```text
前端调用 dispatchChatSession(payload)
  -> 实际发 POST /api/chat/sessions
  -> 后端返回 session_id 和 status
```

---

### 4.2 SSE

SSE 全称是 `Server-Sent Events`。

你可以把它理解成：

**后端不是只回一次结果，而是持续不断地把过程事件推给前端。**

这个项目的 SSE 接口在：

- [backend/app/api/stream/sse.py](/Users/zw/Arcadegent/backend/app/api/stream/sse.py:1)

前端是这样接的：

- [apps/web/src/hooks/useChatSessionController.ts](/Users/zw/Arcadegent/apps/web/src/hooks/useChatSessionController.ts:1)

前端会创建：

```ts
new EventSource(buildChatStreamUrl(sessionId, undefined, clientId))
```

也就是说，当前端拿到 `session_id` 后，就会和后端建立一个持续连接，用来接收聊天处理过程中的实时事件。

---

## 5. 为什么这个项目需要两种通信方式

这是一个很值得理解的问题。

### 5.1 为什么不用纯 HTTP

如果只用普通 HTTP，那么聊天流程会变成：

1. 前端发请求
2. 后端处理很久
3. 最后一次性返回结果

这种方式的问题是：

- 用户等待时完全不知道后端在干什么
- 不利于展示 Agent 调用工具的过程
- 地图、路线、回复文字都只能最后一起出来

---

### 5.2 为什么要加 SSE

这个项目的聊天不是一句简单问答，而是一个“多步骤执行过程”。

后端可能会依次经历：

- 创建会话
- 判断意图
- 切换 subagent
- 调用查询工具
- 调用路线工具
- 生成回复
- 返回最终结果

所以更适合用 SSE，把过程分阶段推回来。

这样前端可以实时显示：

- 当前在执行哪个阶段
- 当前激活的是哪个 subagent
- 工具是否开始执行
- 回复文字是否在逐步生成
- 路线是否已经准备好

---

## 6. 聊天功能里，前端、后端、Python 是怎么联动的

这是最核心的一节。

我们用一个例子来讲：

**用户在前端输入：`帮我找上海附近的 maimai 机厅`**

---

### 6.1 第一步：前端收集用户输入

用户在聊天框输入文字后，前端会触发表单提交逻辑。

聊天总控在：

- [apps/web/src/hooks/useChatSessionController.ts](/Users/zw/Arcadegent/apps/web/src/hooks/useChatSessionController.ts:1)

这个 Hook 负责：

- 创建或复用 `session_id`
- 设置发送状态
- 追加用户消息到前端状态
- 请求浏览器定位
- 调用后端会话接口
- 启动 SSE

这里你可以把它理解成：

**“前端聊天功能的总指挥。”**

---

### 6.2 第二步：前端先发起异步聊天会话

前端不会总是直接调同步 `/api/chat`。

更常用的是调：

- `POST /api/chat/sessions`

对应后端文件：

- [backend/app/api/http/chat.py](/Users/zw/Arcadegent/backend/app/api/http/chat.py:1)

前端发过去的数据大致是：

- `session_id`
- `client_id`
- `message`
- `location`
- `page_size`

这些数据类型在前端和后端两边都有定义：

- 前端类型：[apps/web/src/types.ts](/Users/zw/Arcadegent/apps/web/src/types.ts:1)
- 后端协议：[backend/app/protocol/messages.py](/Users/zw/Arcadegent/backend/app/protocol/messages.py:1)

这一步的关键点是：

**前后端不是随便传数据，而是按约定好的结构传。**

---

### 6.3 第三步：后端接口接收请求

后端的 [backend/app/api/http/chat.py](/Users/zw/Arcadegent/backend/app/api/http/chat.py:1) 会接住这个请求。

然后把请求交给：

- `container.orchestrator.dispatch_chat(request)`

这里的 `container` 来自依赖注入，里面已经准备好了各种长期服务对象。

所以这一步可以理解成：

**FastAPI 负责把 HTTP 请求交给 Python 业务调度器。**

---

### 6.4 第四步：Orchestrator 负责管理会话

具体逻辑在：

- [backend/app/agent/runtime/orchestrator.py](/Users/zw/Arcadegent/backend/app/agent/runtime/orchestrator.py:1)

它做的事包括：

- 没有 `session_id` 就生成一个
- 防止同一个会话被并发重复执行
- 把聊天任务丢到后台异步执行

这一步非常像一个“任务调度入口”。

也就是说：

**HTTP 层不会自己跑完整个聊天流程，而是把这件事交给更底层的 Python Runtime。**

---

### 6.5 第五步：React Runtime 真正执行 Agent

真正干活的是：

- [backend/app/agent/runtime/react_runtime.py](/Users/zw/Arcadegent/backend/app/agent/runtime/react_runtime.py:1)

这里会做很多关键工作：

1. 准备会话状态
2. 记录用户消息
3. 推断用户意图
4. 构建模型上下文
5. 调用 LLM
6. 处理工具调用
7. 保存工具结果到 working memory
8. 推送 SSE 事件
9. 生成最终回复

你可以把 `react_runtime.py` 理解成：

**“Python 侧的聊天执行引擎。”**

---

### 6.6 第六步：Python 根据消息决定接下来做什么

例如用户说“附近”，Runtime 可能推断这是：

- `search_nearby`

如果用户问“怎么去”，可能推断成：

- `navigate`

推断后的意图会影响后续：

- 用哪个 worker
- 开哪些工具权限
- 最终回复该怎么组织

这说明 Python 后端不是“机械转发”，而是在做真正的业务判断。

---

### 6.7 第七步：Agent 调用工具，而不是直接硬编码查所有东西

工具系统核心在：

- [backend/app/agent/tools/registry.py](/Users/zw/Arcadegent/backend/app/agent/tools/registry.py:1)

常见工具包括：

- `db_query_tool`
- `geo_resolve_tool`
- `route_plan_tool`
- `summary_tool`
- `invoke_worker`

流程大致是：

```text
模型输出 tool call
  -> Python ToolRegistry 收到
  -> 检查工具权限
  -> 校验参数
  -> 执行对应工具
  -> 把结果写回 session working memory
```

所以你要明白：

**Python 后端不仅跑 API，还承担了工具调度中心的角色。**

---

### 6.8 第八步：如果需要查机厅，Python 会走数据层

比如调用 `db_query_tool` 后，会进一步使用数据仓库。

本地 JSONL 的实现核心在：

- [backend/app/infra/db/local_store.py](/Users/zw/Arcadegent/backend/app/infra/db/local_store.py:1)

它会做这些事：

- 读入机厅数据
- 生成搜索文本
- 关键词匹配
- 地区筛选
- 机种筛选
- 距离排序
- 分页

所以这一步说明：

**前端并不直接接触真实数据，所有数据筛选逻辑都在 Python 后端。**

---

### 6.9 第九步：如果需要路线，Python 会走地图和导航能力

当用户问“怎么去”或者涉及路线时，后端可能调用：

- `route_plan_tool`
- 或 MCP 动态发现的地图工具

相关逻辑可以从这里串起来看：

- [backend/app/agent/tools/builtin/executors/route_plan.py](/Users/zw/Arcadegent/backend/app/agent/tools/builtin/executors/route_plan.py:1)
- [backend/app/agent/tools/mcp/gateway.py](/Users/zw/Arcadegent/backend/app/agent/tools/mcp/gateway.py:1)
- [backend/app/services/amap_reverse_geocoder.py](/Users/zw/Arcadegent/backend/app/services/amap_reverse_geocoder.py:1)

这一步体现的是：

**Python 后端可以继续向外接地图服务，但前端不直接碰这些复杂逻辑。**

---

### 6.10 第十步：后端一边执行，一边给前端发 SSE 事件

在 Runtime 执行过程中，后端会往 replay buffer 里写事件，再通过 SSE 输出给前端。

常见事件有：

- `session.started`
- `subagent.changed`
- `worker.started`
- `tool.started`
- `tool.completed`
- `assistant.token`
- `navigation.route_ready`
- `assistant.completed`
- `session.failed`

这些事件类型在前端也有明确类型定义：

- [apps/web/src/types.ts](/Users/zw/Arcadegent/apps/web/src/types.ts:1)

这一步很关键，因为它说明：

**前后端不是只传“最终答案”，还在传“执行过程”。**

---

### 6.11 第十一步：前端接收 SSE，实时更新页面

前端仍然是在：

- [apps/web/src/hooks/useChatSessionController.ts](/Users/zw/Arcadegent/apps/web/src/hooks/useChatSessionController.ts:1)

里监听 SSE。

收到不同事件时会做不同处理：

- `session.started`：更新会话状态为运行中
- `subagent.changed`：更新当前活跃 Agent
- `assistant.token`：把回复一点点显示出来
- `navigation.route_ready`：更新地图路线
- `assistant.completed`：把最终回答写入对话
- `session.failed`：显示错误

这一步你可以理解成：

**后端不断发事件，前端不断把事件翻译成 UI 变化。**

---

### 6.12 第十二步：Zustand 把前端状态集中管理起来

这些状态主要由：

- [apps/web/src/stores/appStore.ts](/Users/zw/Arcadegent/apps/web/src/stores/appStore.ts:1)

来保存。

比如：

- 当前会话 ID
- 会话状态
- 历史消息
- 是否正在发送
- 是否正在等待回复
- 当前激活的 subagent
- 地图 artifacts

这说明前端不是收到事件就随便改页面，而是：

**先改状态仓库，再由 React 组件根据状态自动重渲染。**

---

## 7. 机厅浏览功能里，三者又是怎么联动的

聊天只是其中一条链路。

另一个更容易理解的链路是“机厅浏览器”。

---

### 7.1 前端发筛选请求

当前端进入机厅浏览页时，会根据用户选择的条件调用：

- `/api/arcades`
- `/api/regions/provinces`
- `/api/regions/cities`
- `/api/regions/counties`

这些请求封装在：

- [apps/web/src/api/client.ts](/Users/zw/Arcadegent/apps/web/src/api/client.ts:1)

---

### 7.2 后端返回结构化机厅数据

后端的：

- [backend/app/api/http/arcades.py](/Users/zw/Arcadegent/backend/app/api/http/arcades.py:1)
- [backend/app/api/http/regions.py](/Users/zw/Arcadegent/backend/app/api/http/regions.py:1)

会调用数据仓库读取结果，然后通过 DTO 返回统一结构。

比如：

- `PagedArcadeResponse`
- `RegionItemDto`
- `ArcadeShopSummaryDto`

这些 DTO 定义在：

- [backend/app/protocol/messages.py](/Users/zw/Arcadegent/backend/app/protocol/messages.py:1)

---

### 7.3 前端根据返回值更新筛选器和列表

前端拿到这些数据后，会写进：

- [apps/web/src/stores/arcadeBrowserStore.ts](/Users/zw/Arcadegent/apps/web/src/stores/arcadeBrowserStore.ts:1)

里面的状态，例如：

- 省市区列表
- 门店分页结果
- 当前选中的门店
- 地图状态

这就是一个标准的：

**前端请求 -> 后端处理 -> Python 返回数据 -> 前端更新视图**

链路。

---

## 8. 前后端为什么能配合得上

很多人学到这里会问：

“前端怎么知道后端返回什么字段？后端怎么知道前端传什么字段？”

答案是：

**双方靠协议和类型约定来对齐。**

---

### 8.1 后端有协议模型

后端协议定义在：

- [backend/app/protocol/messages.py](/Users/zw/Arcadegent/backend/app/protocol/messages.py:1)

这里定义了很多模型，例如：

- `ChatRequest`
- `ChatResponse`
- `ChatSessionDispatchDto`
- `ChatSessionDetailDto`
- `ArcadeShopSummaryDto`
- `RouteSummaryDto`
- `ClientLocationContext`

这意味着后端知道：

- 一个请求里应该有哪些字段
- 一个响应里应该有哪些字段
- 字段类型是什么

---

### 8.2 前端有对应的 TypeScript 类型

前端类型定义在：

- [apps/web/src/types.ts](/Users/zw/Arcadegent/apps/web/src/types.ts:1)

这里也定义了和后端几乎对应的类型，比如：

- `ChatRequest`
- `ChatResponse`
- `ChatSessionDispatch`
- `ChatSessionDetail`
- `ArcadeSummary`
- `RouteSummary`
- `ClientLocationContext`

所以你可以理解成：

**后端用 Pydantic 约束协议，前端用 TypeScript 约束协议。**

这让联动更稳定，因为不是双方各写各的。

---

## 9. Python 和前端有没有直接关系

严格来说：

**前端不会直接调用 Python 函数。**

前端只会：

- 调 HTTP 接口
- 连 SSE 流

Python 代码对前端来说是“远端服务能力”，不是“本地可调用函数”。

也就是说，它们之间不是函数调用关系，而是网络通信关系。

这点一定要分清。

错误理解是：

- “前端调用 Python”

更准确的理解是：

- “前端调用由 Python 编写的后端接口”

---

## 10. 为什么说这个项目是‘前后端分离，但业务紧密联动’

因为它同时满足两件事：

### 10.1 分离

- 前端代码在 `apps/web`
- 后端代码在 `backend/app`
- 前端和后端通过网络接口通信
- 两边技术栈不同

这叫分离。

### 10.2 紧密联动

- 前端状态依赖后端会话结果
- 后端聊天能力依赖前端传来的位置、消息和 client_id
- 前端地图显示依赖后端返回的 shops、route、view_payload
- SSE 让两边在“执行过程中”实时同步

这叫紧密联动。

所以它不是松散的“前后端各做各的”，而是：

**“结构分离，但行为协同非常强”的系统。**

---

## 11. 用一个超白话比喻再讲一遍

如果你还是觉得抽象，可以把它想成外卖系统：

- 前端 React：外卖 App 界面
- FastAPI 接口：接单系统
- Python Runtime：后厨和调度员
- 数据层：菜单和库存
- 地图服务：骑手导航
- SSE：订单进度实时更新

用户在 App 上点单，相当于在前端发请求。  
后厨收到后开始做菜，相当于 Python 后端跑业务逻辑。  
做菜进度不断回传给 App，相当于 SSE。  
最后菜送到用户面前，相当于最终 JSON / UI 渲染完成。

如果你能接受这个比喻，这个项目的联动关系就基本通了。

---

## 12. 最后把整条链路压缩成一段话

你以后如果要自己讲，可以直接背下面这段：

> 这个项目的前端用 React 负责聊天、机厅浏览和地图展示，前端通过 `fetch` 调用 FastAPI 提供的 HTTP 接口，并通过 `EventSource` 监听 SSE 流。后端由 Python 编写，负责接收请求、管理会话、运行 Agent、调度工具、读取机厅数据和调用地图服务，再把结构化 JSON 或流式事件返回给前端。前后端之间靠统一的请求响应协议和类型定义对齐，所以整个系统形成了“前端发起、后端处理、Python 执行业务、前端实时渲染”的完整闭环。

---

## 13. 推荐你下一步这样学

如果你想真正吃透这套联动关系，建议按这个顺序继续读代码：

1. [apps/web/src/api/client.ts](/Users/zw/Arcadegent/apps/web/src/api/client.ts:1)
2. [backend/app/main.py](/Users/zw/Arcadegent/backend/app/main.py:1)
3. [backend/app/api/http/chat.py](/Users/zw/Arcadegent/backend/app/api/http/chat.py:1)
4. [backend/app/agent/runtime/orchestrator.py](/Users/zw/Arcadegent/backend/app/agent/runtime/orchestrator.py:1)
5. [backend/app/agent/runtime/react_runtime.py](/Users/zw/Arcadegent/backend/app/agent/runtime/react_runtime.py:1)
6. [backend/app/agent/tools/registry.py](/Users/zw/Arcadegent/backend/app/agent/tools/registry.py:1)
7. [backend/app/infra/db/local_store.py](/Users/zw/Arcadegent/backend/app/infra/db/local_store.py:1)
8. [backend/app/api/stream/sse.py](/Users/zw/Arcadegent/backend/app/api/stream/sse.py:1)
9. [apps/web/src/hooks/useChatSessionController.ts](/Users/zw/Arcadegent/apps/web/src/hooks/useChatSessionController.ts:1)
10. [apps/web/src/stores/appStore.ts](/Users/zw/Arcadegent/apps/web/src/stores/appStore.ts:1)

读每个文件时，只回答这 3 个问题：

1. 它从谁那里接数据？
2. 它处理了什么？
3. 它把结果交给谁？

只要你能持续回答这 3 个问题，前端、后端和 Python 的联动关系就会越来越清楚。
