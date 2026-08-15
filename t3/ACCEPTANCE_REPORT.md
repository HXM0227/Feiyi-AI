# T3 验收说明

## 2026-08-13 验收版状态

- **代码实现**：SQLite 索引、按 `chunk_id` 幂等 upsert、确定性中文关键词检索、top-k、citation 组装、默认授权过滤和统一错误响应已实现。
- **自动化测试**：T3 9/9 通过；T0、T1 分别为 12/12、18/18。
- **真实 HTTP 联调**：通过真实 Uvicorn T1/T3/T0 进程复现；T1 输出直接发送给 T3 成功，T3 返回可被 T0 消费。
- **安全行为**：`authorized`/`public` 默认可检索；`unknown`/`restricted` 默认过滤；无命中返回空 `chunks`，不伪造 citation；重复 upsert 不产生重复记录。
- **证据**：`联调证据/2026-08-13-t1-t3-acceptance/`。

## 接口契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| GET | `/readyz` | SQLite 就绪检查 |
| GET | `/v1/capabilities` | 能力发现 |
| POST | `/v1/index/upsert` | 写入或更新 T1 records |
| POST | `/v1/retrieve` | 确定性关键词检索 |

检索 `chunks[]` 每项至少包含：`citation_id`、`source_id`、`title`、`section`、`uri`、`excerpt`、`score`。

## 启动与测试

```powershell
$env:T3_DB_PATH = ".\t3\data\t3.db"
& "..\.venv\Scripts\python.exe" -m uvicorn t3.t3_service.api:create_app --factory --host 127.0.0.1 --port 8103
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t3\tests -v
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t1_t3_acceptance.py --output-dir .\联调证据\2026-08-13-t1-t3-acceptance
```

## 未完成与限制

T3 当前是可复现 MVP，不包含 Embedding、向量数据库、Rerank、FTS/BM25 评测集或生产级召回质量保证。2026-08-13 的 T1/T3 专项验收场景对 T2 使用了临时 Stub；截至 2026-08-15，真实 T2 MVP 已接入 T0 并完成 T0/T1/T2/T3 HTTP 集成收口，最新结论和证据见 `T2_HANDOFF.md` 与 `联调证据/2026-08-15-t2-integration-closure/`。T4/T6 真实模型质量、专业资料复核、授权确认和公开发布审批仍未完成。因此 T3 验收结论为 **有条件通过**，不是生产级检索质量结论。
