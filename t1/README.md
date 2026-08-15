# T1 资料采集、清洗与元数据服务

T1 是非遗 AI 多语种智能解说传播项目的数据底座前置治理模块。它负责在资料进入 T2/T3 前完成基础文本清洗、确定性分块、来源和授权元数据保留，以及 SQLite 资料台账记录。

## 功能边界

已实现：

- `GET /healthz`：健康检查。
- `GET /readyz`：就绪检查。
- `GET /v1/capabilities`：能力发现。
- `GET /v1/sources`：查看本地资料台账（MVP 运维接口）。
- `POST /v1/documents/normalize`：资料清洗、分块和元数据标准化。
- Unicode NFKC、换行/空白归一化。
- 优先按段落和句子边界进行确定性切分。
- 稳定 `<source_id>-0001` 格式 chunk ID。
- SQLite 资料台账和内容哈希。
- `X-Trace-ID`、`X-Request-ID` 透传及统一错误结构。

暂未实现：

- OCR、ASR、视频解析和多模态识别。
- 自动下载或抓取 `source_uri`。
- 向量库、Embedding、Rerank、知识图谱。
- 专家审核工作流、生产级权限和对象存储。

## 启动

在 `t1` 目录的上级目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r t1\requirements-dev.txt
$env:T1_DB_PATH = "./t1/data/t1.db"
python -m uvicorn t1.t1_service.api:create_app --factory --host 127.0.0.1 --port 8101
```

也可以进入 `t1` 目录后执行：

```powershell
python -m uvicorn t1_service.api:create_app --factory --host 127.0.0.1 --port 8101
```

打开 OpenAPI：`http://127.0.0.1:8101/docs`。

## 接口示例

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8101/v1/documents/normalize `
  -Headers @{"X-Trace-ID"="trace-demo"; "X-Request-ID"="request-demo"} `
  -ContentType "application/json" `
  -InFile .\t1\examples\normalize-request.json
```

T0 接入时只需使用：

```text
T0_MODE=http
T1_BASE_URL=http://127.0.0.1:8101
```

T0 当前将 `source_id` 作为请求必填字段，因此 T1 MVP 验证并原样保留调用方传入的 `source_id`。正文按照现有 v1.0.0 兼容约定从 `documents[].metadata.text` 读取；不要在顶层新增 `content` 或 `text`。

## 数据治理规则

- `authorization_status` 原样保留，不能把 `restricted` 或 `unknown` 升级为 `authorized`。
- `publish=true` 不改变授权状态，也不等价于公开发布；受限/未知资料会产生 warning。
- T1 不负责在线检索授权过滤，T3 必须在检索阶段过滤 `restricted`/`unknown`。
- 缺少 `metadata.text` 时返回 `rejected[]`，不生成占位文本。
- 没有预提取文本的 image/audio/video 返回 `UNSUPPORTED_MEDIA_FOR_MVP`。
- 不自动访问 `source_uri`。

## 测试

```powershell
python -m unittest discover -s t1\tests -v
```

测试不访问外网、不调用模型。运行完整测试前必须先安装 `t1\requirements-dev.txt` 中的依赖；如果缺少 FastAPI、Pydantic 或 HTTPX，测试会失败或 API 测试被跳过。`/readyz` 会实际执行 SQLite `SELECT 1` 探测，数据库不可用时返回 HTTP 503。

## 2026-08-13 验收版状态

- T1 自动化测试：18/18 通过；T0/T1/T3：12/12、18/18、9/9。
- 真实 HTTP：T0 → T1 normalize → T3 upsert 的链路已在 `联调证据/2026-08-13-t1-t3-acceptance/` 复现。
- 异常规则：非法输入统一返回 `VALIDATION_ERROR`；`unknown`/`restricted` 原样保留；`publish=true` 不升级授权状态。
- 结论：T1 MVP 有条件通过，不等于真实模型质量、专业资料复核或公开发布授权已完成。详见 `t1/ACCEPTANCE_REPORT.md`。
## 与 T0 的契约问题与后续事项

1. 分工表写有“source_id 由 T1 创建”，但 T0 v1.0.0 的 `KnowledgeDocument` 将 `source_id` 设为必填。当前 MVP 以 T0 实际请求为准，保留传入 ID；如要由 T1 生成，需先提交契约变更提案。
2. T0 第 5 节只冻结了 `records[]` 和 chunk 的最小字段，没有完全冻结 T1 record 的扩展元数据结构。本实现保留常用治理元数据，并在 response 中省略原始 `metadata.text`，避免把完整正文重复传播。
3. T0 说明书要求消费者忽略未知字段，但 T0 部分 Pydantic 响应模型当前配置为禁止未知字段。T1 的请求模型采用忽略未知字段；response 的扩展字段需在 T0 侧确认后再增加必需依赖。
4. 当前 T1 仅保证 T0 硬性需要的 `source_id`、`title`、`source_uri`、`authorization_status`、`chunks[].chunk_id` 和 `chunks[].text`。
