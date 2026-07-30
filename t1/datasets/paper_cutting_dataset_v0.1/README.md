# 剪纸真实资料集（T1 MVP 首批）

## 1. 用途

本目录保存“剪纸”主题的首批真实来源资料，供 T1 的文本清洗、稳定分块、元数据透传和来源台账功能测试使用。

- 检索与整理日期：2026-07-28
- 资料数量：5 条
- 内容语言：简体中文（`zh-CN`）
- 当前用途：内部开发、联调和人工复核
- 发布开关：`publish=false`
- 授权状态：全部暂记为 `unknown`

## 2. 来源范围

首批来源优先使用：

1. 联合国教科文组织非物质文化遗产名录页面；
2. 中国非物质文化遗产网·中国非物质文化遗产数字博物馆项目页面。

本目录没有下载或复用网页图片、音视频，也没有整页复制来源正文。`metadata.text` 是根据可核实事实重新组织的项目组摘要。

## 3. 文件说明

| 文件 | 作用 |
|---|---|
| `paper-cutting-normalize-request.json` | 可直接提交给 `POST /v1/documents/normalize` 的 T1 请求 |
| `sources.csv` | 人工可读的来源和授权台账 |
| `paper-cutting-raw-notes.md` | 检索事实、写作边界与待复核点 |
| `review-checklist.md` | 项目组、老师、专家或传承人的逐条复核表 |
| `paper-cutting-normalize-response.json` | T1 实际处理结果（运行后生成） |
| `paper-cutting-source-ledger.json` | T1 SQLite 来源台账导出（运行后生成） |
| `paper-cutting-t1.db` | 本资料集独立使用的 T1 测试数据库（运行后生成） |
| `TEST_REPORT.txt` | 导入与回归测试结果（运行后生成） |

## 4. 使用方式

在工作区根目录运行：

```powershell
.\.venv\Scripts\python.exe .\t1\datasets\paper_cutting_dataset_v0.1\run_t1_import.py
```

脚本会使用 FastAPI `TestClient` 调用真实 T1 接口，而不是绕过接口直接调用处理函数；响应与来源台账会保存在本目录。

## 5. 内容和版权边界

公开可访问不等于获得了复制、改编或商业传播授权。因此当前所有记录保持：

```json
"authorization_status": "unknown"
```

不得仅因为来源是权威网站，就把状态改成 `authorized`。如需进入面向公众的正式知识库，至少需要完成：

1. 核对事实和来源页面；
2. 确认摘要、引用、网页内容和相关素材的使用许可；
3. 由项目负责人指定复核人；
4. 对地方性和专业性内容征求项目保护单位、专家或代表性传承人意见；
5. 填写真实的 `reviewer`、`reviewed_at` 和复核结论；
6. 由后续模块继续过滤 `restricted` 与 `unknown` 资料。

## 6. 当前不包含的内容

本批次不包含网页自动采集器、图片版权素材、音视频、传承人口述记录、长篇原文、自动更新任务，也不表示已经完成专家审核。
