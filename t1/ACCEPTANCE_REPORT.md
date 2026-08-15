# T1 验收说明

## 2026-08-13 验收版状态

- **代码实现**：T1 资料规范化、确定性分块、来源台账、授权状态保留、统一错误响应和追踪 ID 已实现。
- **自动化测试**：T1 18/18 通过；与 T0、T3 的完整测试分别为 12/12、9/9。
- **真实 HTTP 联调**：通过 `t3/smoke/run_t1_t3_acceptance.py` 复现。T1 真实 Uvicorn 服务可被 T0 调用，输出可直接被 T3 接收。
- **异常与安全规则**：非法输入返回 `VALIDATION_ERROR`；缺失正文不生成占位文本；`unknown`/`restricted` 保留原值；`publish=true` 不升级授权状态。
- **证据**：`联调证据/2026-08-13-t1-t3-acceptance/`。

## 接口契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 健康检查 |
| GET | `/readyz` | SQLite 就绪检查 |
| GET | `/v1/capabilities` | 能力发现 |
| GET | `/v1/sources` | 来源台账查询 |
| POST | `/v1/documents/normalize` | 资料清洗、规范化和分块 |

标准记录字段包括 `source_id`、`title`、`source_uri`、`media_type`、`authorization_status`、`metadata`、`chunks`；chunk 至少包括稳定的 `chunk_id`、`text`、`sequence`，并可带 `section`、`language`。

## 启动与测试

```powershell
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t1\tests -v
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t1_t3_acceptance.py --output-dir .\联调证据\2026-08-13-t1-t3-acceptance
```

## 未完成与限制

T1 MVP 不包含 OCR、ASR、视频解析、自动抓取、Embedding、向量库或专家审核。真实模型质量、专业资料复核、全部授权确认和公开发布审批不属于本轮已完成内容。因此本模块结论为 **有条件通过**，不能等同于生产级数据治理或公开发布许可。
