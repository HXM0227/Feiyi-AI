# T2 非遗知识图谱关联服务 MVP

## 1. 当前状态

T2 已实现为独立 FastAPI + SQLite MVP，默认监听 `127.0.0.1:8102`，并完成与当前 T0/T1/T3 基线的真实 HTTP 集成收口验证。

已实现：

- 实体、别名、关系、来源和 chunk 回链存储；
- `entity_id` / `relation_id` 幂等 upsert；
- 标准名称、别名、实体类型、实体 ID、关系谓词和一跳关系查询；
- `authorized` / `public` 默认可见；
- `unknown` / `restricted` 默认过滤且显式请求不能绕过；
- 来源授权状态变化后按当前状态过滤；
- 非法关系引用校验；
- 统一错误响应；
- `X-Trace-ID` / `X-Request-ID` 透传或自动生成；
- SQLite readiness；
- T0 HTTP 入库编排和 T2 失败 `partial` 降级；
- 自动化测试、统一真实 HTTP 验收脚本和验收证据。

## 2. 明确边界

本版本不包含自动实体/关系抽取、真实大模型、Neo4j、Embedding、向量数据库、Rerank、复杂图推理、专业事实复核、正式授权审核或生产部署。

T0 请求中的 `entities` / `relations` 是人工标注或由可信上游明确提供的结构化数据；T2 不会根据正文猜测知识。

## 3. 安装与启动

```powershell
cd "C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork"
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m pip install -r t2\requirements.txt
$env:T2_DB_PATH = "C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\data\t2.db"
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m uvicorn t2_service.api:create_app --factory --app-dir t2 --host 127.0.0.1 --port 8102
```

## 4. 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 存活检查 |
| GET | `/readyz` | SQLite 就绪检查 |
| GET | `/v1/capabilities` | 能力发现 |
| POST | `/v1/graph/upsert` | 幂等写入/更新来源、实体、别名和关系 |
| POST | `/v1/graph/query` | 按实体、名称、别名、类型或关系查询 |
| GET | `/v1/graph/entities/{entity_id}` | 实体详情和一跳关系 |
| GET | `/v1/graph/relations` | 关系查询 |

详细契约见 `C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\t2\docs\interface.md`。

## 5. T0/T1/T2/T3 链路

```text
T0 /v1/knowledge/ingest
  -> T1 /v1/documents/normalize
  -> T3 /v1/index/upsert
  +  T2 /v1/graph/upsert
```

T2 失败而 T3 已成功时，T0 返回 `status=partial` 和包含 T2 的 warnings，保留 T3 已完成索引，不回滚，也不生成无来源图谱。

## 6. 测试

自动化测试：

```powershell
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" -m unittest discover -s t2/tests -v
```

统一真实 HTTP 验收：

```powershell
& "C:\Users\sunbu\Documents\非遗AI解说\.venv\Scripts\python.exe" t2\smoke\run_t2_integration_acceptance.py `
  --t0-port 8120 --t1-port 8121 --t2-port 8122 --t3-port 8123 `
  --partial-t0-port 8129 `
  --evidence "联调证据\2026-08-15-t2-integration-closure"
```

最新证据：`C:\Users\sunbu\Documents\非遗AI解说\Feiyi-AI-fork\联调证据\2026-08-15-t2-integration-closure`。
