# Arcadegent Docs

这里是公开仓库的文档入口。对外只公开两类文档：

- `guidings/`：面向使用和扩展的指南。
- `dev-details/`：已经落地或接近落地的工程细节。

计划、issue、历史草稿、数据链路细节和迁移材料只作为本地归档，不进入公开文档入口。

## 推荐阅读顺序

1. [项目 README](../README.md)：安装、运行、部署和 API 入口。
2. [Arcadegent 项目说明文档（演示版）](./guidings/arcadegent-demo-project-brief.md)：适合演示、路演或向他人快速讲解项目的说明稿。
3. [Arcadegent 小白入门拆解](./guidings/arcadegent-beginner-walkthrough.md)：面向零基础读者的项目结构、请求链路和面试讲法。
4. [Arcadegent 简历项目写法](./guidings/arcadegent-resume-snippets.md)：按简历项目经历格式整理的技术栈、项目简介和 bullet。
5. [Arcadegent 岗位应聘准备手册](./guidings/arcadegent-job-application-prep.md)：围绕岗位要求、项目匹配、面试话术和补短板清单整理的求职材料。
6. [Arcadegent 简历与自我介绍成品稿](./guidings/arcadegent-resume-and-self-intro-final.md)：可直接用于简历、项目介绍和自我介绍的成品文案。
7. [Arcadegent 简历终稿与面试口语稿](./guidings/arcadegent-resume-final-copy.md)：压缩后的可直接复制版本，适合简历终稿和面试前速记。
8. [Arcadegent 面试追问与参考回答](./guidings/arcadegent-interview-followups-qa.md)：围绕项目高频追问整理的答题卡。
9. [Arcadegent 模拟面试 20 题](./guidings/arcadegent-mock-interview-20.md)：按短答版、展开版和可能追问整理的临场练习题库。
10. [Arcadegent 项目难点与解决办法](./guidings/arcadegent-project-challenges-and-solutions.md)：从 Agent、RAG、FAISS、多模态、MCP 和地图能力角度整理的项目难点复盘。
11. [前端、后端与 Python 联动说明](./guidings/frontend-backend-python-linkage.md)：从请求、协议、SSE 和 Agent 流程解释三者如何协同工作。
12. [Builtin Tool Manifest 指南](./guidings/builtin-tool-manifest-guide.md)：新增内建工具时的 manifest / schema 写法。
13. [项目面试题库与深度追问](./guidings/interview-question-bank.md)：按架构、Agent、前端、数据和部署整理的面试问答。
14. [Agent 地图 Artifacts 渲染说明](./dev-details/agent-map-artifacts-rendering.md)：后端 artifacts 契约与前端地图渲染。
15. [浏览器定位与逆地理编码](./dev-details/browser-location-reverse-geocoding.md)：定位、逆地理和 agent 上下文注入链路。
16. [Agent Context Payload Design](./dev-details/agent-context-payload-design.md)：agent 上下文 payload 的结构和约束。
17. [动态工具注册实现说明](./dev-details/dynamic-tool-registry-implementation.md)：builtin 与 MCP 工具注册链路。

## 公开边界

以下内容不要写入公开文档或提交到仓库：

- 真实机厅数据、抓取产物、运行缓存、QA 报告和数据库导出。
- 生产 `.env`、API key、Supabase service role key、地图服务密钥。
- 可反推出私有数据规模、抓取批次或生产库结构的细节。
- 计划草稿、issue 讨论、上线清单、临时调试输出、截图、浏览器 traces 和本机绝对路径。

如果必须描述数据链路，使用“兼容 JSONL 数据源”“私有数据目录”“数据库读模型”这类抽象表述；具体文件名、批次产物和导入脚本放在私有文档里。

## 文档维护约定

1. README 只保留用户真正需要的安装、运行、部署和排障信息。
2. 新增对外指南放入 `guidings/`。
3. 新增对外工程细节放入 `dev-details/`。
4. 含真实数据路径、抓取批次、数据库迁移、计划或 issue 讨论的材料只放本地归档。
