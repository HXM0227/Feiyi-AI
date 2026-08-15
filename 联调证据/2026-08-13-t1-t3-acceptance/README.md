# T1/T3 验收版真实 HTTP 联调证据

- **测试日期**：2026-08-13
- **Git commit**：`ac3ed99`（验收执行基线；工作区另有本轮未提交修改，最终状态见仓库 `git status`）。
- **Python**：使用 `C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe`；本轮实测 Python 3.14.5。
- **依赖**：FastAPI 0.140.0、Pydantic 2.13.4、HTTPX 0.28.1、Uvicorn 0.35.x（共享工作区环境）。

## 服务启动

验收脚本 `t3/smoke/run_t1_t3_acceptance.py` 启动真实 Uvicorn 进程：

```powershell
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t1_t3_acceptance.py --output-dir .\联调证据\2026-08-13-t1-t3-acceptance
```

- T1：`t1.t1_service.api:create_app`，`127.0.0.1:8111`
- T3：`t3.t3_service.api:create_app`，`127.0.0.1:8113`
- T0：`t0.t0_orchestrator.api:create_app`，`127.0.0.1:8110`

T2、T4、T5、T6、T8、T9 使用脚本内临时 HTTP Stub，仅用于验证 T0 的 HTTP 编排边界和错误处理；不是这些模块的实现或模型质量验收。

## 测试数据

数据为脱敏的合成联调资料，URI 使用 `example.org`，不包含 API Key、Token、个人隐私或未公开原始资料。资料分别使用 `authorized`、`unknown`、`restricted` 三种授权状态。

## 已验证场景

1. T1 `/healthz`、`/readyz`、`POST /v1/documents/normalize` 真实 HTTP 启动和调用。
2. T3 `/healthz`、`/readyz`、`POST /v1/index/upsert`、`POST /v1/retrieve` 真实 HTTP 启动和调用。
3. T0 `/v1/knowledge/ingest` 真实调用 T1 normalize，再将 T1 输出真实发送给 T3 upsert。
4. T1 输出直接作为 T3 输入，字段可兼容消费。
5. 重复 chunk upsert 幂等，未产生重复索引记录。
6. T3 默认检索只返回授权资料，`unknown`、`restricted` 不默认公开检索。
7. 无命中返回 `{"chunks": []}`，不伪造 citation。
8. citation 字段包含 `citation_id`、`source_id`、`title`、`section`、`uri`、`excerpt`、`score`。
9. T0 `/v1/guide/query` 能消费 T3 citation；T4 使用 Stub 返回示范答案。
10. 停止 T3 后，T0 `/v1/guide/query` 返回 `DOWNSTREAM_MODULE_ERROR`，不会生成无依据答案。
11. T1/T3/T0 请求和响应保存了追踪 ID 相关证据；T0 已补充响应头透传中间件。
12. T1 非法输入返回稳定 `VALIDATION_ERROR`。

## 结果

`test-results.txt` 和 `summary.json` 中的 14 项断言全部 PASS。请求和响应分别位于 `requests/`、`responses/`，异常场景位于 `errors/`，服务日志位于 `logs/`。

## 限制与未完成项

- T2 当前是 Stub，不能据此宣称 T2 已完成。
- T4 当前是 Stub，不能据此宣称真实大模型生成质量、事实准确性或多语种质量已通过。
- T6 当前是 Stub；本环境没有以真实 DashScope 模型完成多模态质量验收。
- 本轮只验证 T1/T3 MVP 的接口、数据边界、确定性关键词检索、授权过滤、幂等和错误安全行为。
- 没有完成专业资料逐条复核、专家审核、所有资料授权确认或公开发布审批；`unknown`/`restricted` 不能视为可公开发布。
- 当前关键词检索不是 Embedding、向量数据库或 Rerank 方案，不代表生产级召回率。
- 证据目录中的 SQLite 数据库和日志是本地运行产物，提交时应按仓库策略排除或仅保留必要脱敏证据。

## 结论

**T1/T3 验收版：有条件通过。**

代码实现、T0/T1/T3 自动化测试、真实 Uvicorn HTTP 链路、T1→T3 字段兼容、授权过滤、无命中、幂等、追踪 ID 和下游不可用安全拒绝均已复现通过；但其他模块真实实现、真实模型质量、专业资料复核、授权确认和生产部署尚未完成。
