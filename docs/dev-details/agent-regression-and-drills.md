# Agent 回归评测与故障演练

这套回归主要覆盖四条最容易悄悄退化的 Agent 链路：

- 固定问句集：`backend/app/tests/regression/fixtures/agent_golden_questions.json`
- 意图路由与 query rewrite 稳定性：`backend/app/tests/regression/test_agent_regression_suite.py`
- 工具失败注入与优雅降级：同一 regression suite 内的 failure drill
- SSE 回放顺序与 offset 恢复：同一 regression suite 内的 replay drill
- 前端黄金链路：`apps/web/tests/e2e/arcade-browser-map.spec.ts` 里的 `golden chain covers ask, streaming route map, and knowledge index status`

## 后端回归

```bash
backend/.venv/bin/python backend/scripts/run_agent_regression.py
```

等价于跑：

```bash
backend/.venv/bin/python -m pytest \
  backend/app/tests/regression \
  backend/app/tests/unit/test_stream_event_contract.py \
  backend/app/tests/integration/test_api.py::test_chat_session_detail_supports_legacy_route_payload
```

## 前端黄金链路

```bash
cd apps/web
npm run test:e2e:golden
```

该用例用 Playwright mock 住 API、SSE 和 AMap SDK，验证从发问、接收流式路线事件、渲染地图卡片，到进入知识库查看/上传索引状态的完整链路。
