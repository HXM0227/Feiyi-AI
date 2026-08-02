# T3 MVP 测试与联调报告

测试日期：2026-08-02
分支：`feature/t3-mvp`

## 自动化测试

在仓库根目录执行：

```powershell
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t3\tests -v
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t1\tests -v
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t0\tests -v
```

结果：

- T3：9 tests，OK；
- T1：18 tests，OK；
- T0：12 tests，OK；
- T3 Python 文件 `py_compile` 检查通过；
- `git diff --check` 通过。

## 真实 HTTP 联调

执行：

```powershell
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t0_t1_t3_http.py
```

结果：

- T0、T1、T3 通过真实 HTTP 启动；
- T2 使用临时 HTTP Stub，仅用于满足 T0 入库编排链路；
- T0 `/v1/knowledge/ingest` 返回 HTTP 200、`status=completed`、`accepted_count=2`；
- T3 `/v1/retrieve` 返回 HTTP 200；
- `authorized` 资料可检索；
- `unknown` 资料未出现在默认检索结果中；
- `citation_id`、`source_id`、`title`、`section`、`uri`、`excerpt`、`score` 均存在；
- T3 请求头 `X-Trace-ID`、`X-Request-ID` 正常透传。

精简证据位于：

```text
联调证据/2026-08-02-t0-t1-t3/
```

数据库和日志属于运行产物，不纳入提交。

## 当前限制

- T2 仍使用临时 Stub，尚未完成真实 T2 联调；
- T0 的完整导览问答还依赖 T4、T5、T6、T8 等模块，当前不进行端到端生产链路验证；
- 关键词检索是 MVP 方案，不代表最终向量检索或专业资料质量审核结果。
