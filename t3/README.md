# T3 资料索引与检索 MVP

T3 位于 T1 清洗模块之后，为 T0 提供可追溯、可解释的最小资料索引和关键词检索服务。

## MVP 边界

- FastAPI + SQLite；
- 接收 T1 `/v1/documents/normalize` 返回的 `records`；
- 以 `chunk_id` 为唯一键幂等 upsert；
- 使用 Unicode NFKC、中文二字符 n-gram 和字母数字 token 做确定性关键词匹配；
- 分数按查询项覆盖率计算，按 `score` 降序、`chunk_id` 升序稳定排序；
- 默认只检索 `authorized` 和 `public`，请求显式提供 `filters.authorization_status` 时使用请求列表；
- 不使用 Embedding、向量数据库、Rerank、模型或外部网络；
- 保留 source、chunk、语言、版本、授权状态和元数据，响应只暴露 T0 已确认的核心引用字段。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 存活检查 |
| GET | `/readyz` | SQLite 就绪检查 |
| GET | `/v1/capabilities` | 能力发现 |
| POST | `/v1/index/upsert` | 写入或更新 T1 records |
| POST | `/v1/retrieve` | 关键词检索 |

检索结果的每个 `chunks[]` 项包含：`citation_id`、`source_id`、`title`、`section`、`uri`、`excerpt`、`score`。
无命中时返回 `{"chunks": []}`，不会伪造引用。

## 启动

在仓库根目录执行：

```powershell
$env:T3_DB_PATH = "./t3/data/t3.db"
& ".\.venv\Scripts\python.exe" -m uvicorn t3.t3_service.api:create_app --factory --host 127.0.0.1 --port 8103
```

如果仓库内 `.venv` 没有依赖，使用工作区上级环境：

```powershell
& "..\.venv\Scripts\python.exe" -m uvicorn t3.t3_service.api:create_app --factory --host 127.0.0.1 --port 8103
```

可选环境变量：`T3_DB_PATH`、`T3_API_TOKEN`、`T3_CONTRACT_VERSION`、`T3_MAX_TOP_K`、`T3_MAX_EXCERPT_CHARS`。

## 示例调用

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8103/v1/index/upsert `
  -Headers @{"X-Trace-ID"="trace-t3-demo"; "X-Request-ID"="request-t3-demo"} `
  -ContentType "application/json" -InFile .\t3\examples\upsert-request.json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8103/v1/retrieve `
  -Headers @{"X-Trace-ID"="trace-t3-retrieve"; "X-Request-ID"="request-t3-retrieve"} `
  -ContentType "application/json" -InFile .\t3\examples\retrieve-request.json
```

## 测试

```powershell
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t3\tests -v
```

测试不访问外网、不调用模型。真实 HTTP 冒烟脚本位于 `t3/smoke/run_smoke.py`。

## 2026-08-13 验收版状态

- T3 自动化测试：9/9 通过；T0/T1：12/12、18/18。
- 真实 HTTP：T1 输出直接发送 T3 upsert 成功；T3 citation 可被 T0 消费。
- 授权过滤、无命中空结果、重复 upsert 幂等、错误响应和追踪 ID 已验证。
- 结论：T3 MVP 有条件通过，不等于 Embedding/向量/Rerank 或生产召回质量验收。详见 `t3/ACCEPTANCE_REPORT.md` 和 `联调证据/2026-08-13-t1-t3-acceptance/`。
## 与 T0/T1 的调用链

```text
T0 POST /v1/knowledge/ingest
  -> T1 POST /v1/documents/normalize
  -> T3 POST /v1/index/upsert
  -> T2 POST /v1/graph/upsert

T0 POST /v1/guide/query or /v1/content/generate
  -> T3 POST /v1/retrieve
```

T0 的 Pydantic `Citation` 模型当前严格依赖 `citation_id`、`source_id`、`title`、`section`、`uri`、`excerpt`、`score`，因此 T3 第一版不要求 T0 消费额外字段。`X-Trace-ID` 和 `X-Request-ID` 会在请求和响应头之间透传；未提供时由 T3 生成。
