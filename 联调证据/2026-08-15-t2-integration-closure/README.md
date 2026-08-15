# T2 集成收口与验收加固证据

- 测试日期：2026-08-15（北京时间）
- 仓库：`C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork`
- Git commit：`ac3ed998bbeff77a2d720ba47c593265ed1e34ce`
- 解释器：`C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe`
- Python：3.14.5

## 1. 验证类型

本目录包含 **真实 Uvicorn HTTP** 验证，不是只使用 TestClient/ASGI，也不是 Mock/Stub 联调。

- T0/T1/T2/T3：真实本地 Uvicorn 进程；
- T1/T2/T3：使用本目录内独立 SQLite 数据库，避免污染历史联调数据；
- 知识实体和关系：人工标注测试数据；
- 自动实体/关系抽取：未启用、未宣称完成；
- 真实大模型质量、专业复核、正式授权审核：不属于本轮已通过内容。

## 2. 独立服务和端口

| 模块 | 端口 | 数据库/配置 |
|---|---:|---|
| T0 正常链路 | 8120 | `T1_BASE_URL=:8121`、`T2_BASE_URL=:8122`、`T3_BASE_URL=:8123` |
| T1 | 8121 | `t1-closure.db` |
| T2 | 8122 | `t2-closure.db` |
| T3 | 8123 | `t3-closure.db` |
| T0 降级链路 | 8129 | T1/T3 正常，`T2_BASE_URL=http://127.0.0.1:8199`（未监听） |

启动命令形式：

```powershell
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t1_service.api:create_app --factory --app-dir t1 --host 127.0.0.1 --port 8121
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t2_service.api:create_app --factory --app-dir t2 --host 127.0.0.1 --port 8122
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t3_service.api:create_app --factory --app-dir t3 --host 127.0.0.1 --port 8123
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t0_orchestrator.api:create_app --factory --app-dir t0 --host 127.0.0.1 --port 8120
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t0_orchestrator.api:create_app --factory --app-dir t0 --host 127.0.0.1 --port 8129
```

完整环境变量和进程日志见 `logs/`。统一脚本：

```powershell
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" t2\smoke\run_t2_integration_acceptance.py `
  --t0-port 8120 --t1-port 8121 --t2-port 8122 --t3-port 8123 `
  --partial-t0-port 8129 `
  --evidence "联调证据\2026-08-15-t2-integration-closure"
```

## 3. 已通过结论

1. T0/T1/T2/T3 health 和 T1/T2/T3 ready 均通过；
2. T0 → T1 → T3/T2 正常入库返回 `status=completed`；
3. T2 实体和关系返回真实 `source_id/chunk_id`；
4. T3 citation 的 `source_id` 与由 citation ID 表达的 chunk ID 和 T2 回链一致；
5. 相同 ingestion 重复执行，T2/T3 不生成重复行，返回计数稳定；
6. `authorized`、`public` 默认可见；
7. `unknown`、`restricted` 默认不可见；
8. 不能通过 name、alias、entity_id、predicate、实体详情或关系列表绕过授权过滤；
9. T2 指向未监听的 8199 时，T0 返回 HTTP 200、`status=partial`，warnings 明确指出 T2 图谱失败；
10. partial 场景下 T3 已入库内容仍可检索，T2 正常服务中没有凭空生成该场景的图谱数据；
11. 正常和 partial 响应均保留 `X-Trace-ID` / `X-Request-ID` 追踪头；
12. 自动化回归：T0 12、T1 18、T2 6、T3 9 项通过，compileall 和 `git diff --check` 通过。

## 4. 关键证据

- `requests/normal-ingest-001.json`
- `responses/normal-ingest-001.json`
- `responses/normal-ingest-repeat-001.json`
- `responses/chain-t2-query-001.json`
- `responses/chain-t3-retrieve-001.json`
- `responses/chain-t2-query-repeat-001.json`
- `responses/chain-t3-retrieve-repeat-001.json`
- `responses/auth-upsert-001.json`
- `responses/auth-upsert-repeat-001.json`
- `responses/auth-default-authorized-001.json`
- `responses/auth-default-public-001.json`
- `responses/auth-default-unknown-001.json`
- `responses/auth-default-restricted-001.json`
- `responses/auth-bypass-unknown-*.json`
- `responses/auth-bypass-restricted-*.json`
- `responses/partial-ingest-001.json`
- `responses/partial-t3-retrieve-001.json`
- `responses/partial-t2-query-001.json`
- `responses/sqlite-idempotency-counts.json`
- `responses/automated-test-summary.json`
- `test-results.txt`
- `logs/*.log`

## 5. 幂等数据库结果

统一测试来源 `SRC-T2-CLOSURE-CHAIN-20260815` 重复入库后：

- T1 source ledger：1 条该来源；
- T2 source：1 条；
- T2 chunk：1 条；
- T2 entity source 关联：2 条（两个实体各一条）；
- T2 relation：1 条；
- T3 chunk：1 条。

详细计数见 `responses/sqlite-idempotency-counts.json`。

## 6. 运行产物与 Git 交付范围

本地完整证据目录保留独立 SQLite 数据库、Uvicorn/单元测试日志和进程元数据，便于现场复核；Git 交付基线只纳入脱敏请求、响应、错误、测试摘要和必要说明。以下可再生运行产物保留在用户工作区，但由 `.gitignore` 排除，不进入 staged changes：

- `*.db`、`*.db-shm`、`*.db-wal`；
- `*.log`；
- `logs/isolated-processes.json`；
- `__pycache__/`、`*.pyc`。

仓库已有历史运行产物未删除、未覆盖。请求/响应中未写入 API Key、Token 或真实隐私数据。

原始控制台汇总 `test-results-automated.txt` 因包含 PowerShell 混合编码诊断，仅保留在本地完整证据目录，不纳入 Git 交付；可审查结论以 `test-results.txt` 和 `responses/automated-test-summary.json` 为准。

## 7. 边界

本轮达到的是 **T2 MVP 集成收口和条件性验收基线**，不是生产标准。尚未完成：

- 自动实体抽取；
- 自动关系抽取；
- 专业资料事实复核；
- 正式授权审核流程；
- 真实模型质量验收；
- 生产部署、鉴权、限流、监控、备份和灾备；
- Neo4j、Embedding、向量库、Rerank 和复杂图推理。
