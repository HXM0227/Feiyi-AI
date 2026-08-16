# 剪纸真实资料集（T1 可用版）

## 1. 用途

本目录保存“剪纸”主题的首批真实来源资料，供 T1 清洗与分块、T3 索引与检索，以及后续智能解说链路使用。

- 初次检索与整理日期：2026-07-28
- 可用状态更新日期：2026-08-16
- 数据版本：`2026-08-16-v1.0`
- 资料数量：5 条
- 内容语言：简体中文（`zh-CN`）
- 当前用途：项目开发、联调、演示与后续模块使用
- 发布开关：`publish=true`
- 授权状态：全部为 `authorized`
- 复核状态：项目组已确认无需额外复核，可直接用于本项目

## 2. 来源范围

首批来源包括：

1. 联合国教科文组织非物质文化遗产名录页面；
2. 中国非物质文化遗产网·中国非物质文化遗产数字博物馆项目页面。

本目录没有下载网页图片、音视频或整页复制来源正文。`metadata.text` 是根据来源中可核实的信息重新组织的项目资料摘要。

## 3. 文件说明

| 文件 | 作用 |
|---|---|
| `paper-cutting-normalize-request.json` | 可直接提交给 `POST /v1/documents/normalize` 的 T1 请求 |
| `paper-cutting-normalize-response.json` | T1 实际清洗和分块结果 |
| `sources.csv` | 人工可读的来源与使用状态台账 |
| `paper-cutting-raw-notes.md` | 来源事实、摘要范围和编辑边界 |
| `review-checklist.md` | 历史文件名保留，现记录本批资料的可用状态确认结果 |
| `paper-cutting-source-ledger.json` | T1 SQLite 来源台账导出 |
| `paper-cutting-t1.db` | 本资料集独立使用的 T1 测试数据库（本地生成，不提交 Git） |
| `run_t1_import.py` | 运行真实 T1 接口导入的脚本 |
| `TEST_REPORT.txt` | 最新导入和回归测试结果 |

## 4. 使用方式

在仓库根目录运行：

```powershell
& "..\.venv\Scripts\python.exe" .\t1\datasets\paper_cutting_dataset_v0.1\run_t1_import.py
```

脚本使用 FastAPI `TestClient` 调用真实 T1 接口，并重新生成规范化响应、来源台账和本地测试数据库。

## 5. 当前数据状态

本批 5 条记录均设置为：

```json
{
  "authorization_status": "authorized",
  "publish": true
}
```

因此这些记录可以进入 T3 索引，并被 T0 当前允许的 `authorized/public` 检索过滤器返回。

“无需额外复核”表示项目组已经确认本批网络来源整理资料可直接用于当前项目，不再把专业复核或授权确认作为入库、检索和演示的阻塞条件。

## 6. 内容边界

- 保留 `source_id` 和 `source_uri`，确保结果可追溯。
- 正文是项目组摘要，不冒充来源网页原文。
- 不使用来源网页中的图片和音视频文件。
- 不对来源未覆盖的历史、传承谱系、宗教仪式或禁忌作延伸断言。
- 后续若修改正文，应同步提升 `metadata.version` 并重新运行导入脚本。
