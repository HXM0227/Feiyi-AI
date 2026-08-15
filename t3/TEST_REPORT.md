# T3 MVP 测试与验收报告

测试日期：2026-08-13
验收执行基线：`ac3ed99`；本轮文档和 T0 API 修改未提交，最终状态见 `git status`

## 自动化测试

在仓库根目录使用共享工作区环境执行：

```powershell
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t0\tests -v
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t1\tests -v
& "..\.venv\Scripts\python.exe" -m unittest discover -s .\t3\tests -v
```

结果：

- T0：12/12 通过；
- T1：18/18 通过；
- T3：9/9 通过；
- `py_compile`：T0 API 和 T3 验收脚本通过；
- `git diff --check`：通过。

## 真实 HTTP 验收

执行：

```powershell
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t1_t3_acceptance.py --output-dir .\联调证据\2026-08-13-t1-t3-acceptance
```

脚本启动真实 Uvicorn T1、T3、T0，使用合成且脱敏资料，并为 T2、T4、T5、T6、T8、T9 提供临时 HTTP Stub。14 项断言全部 PASS：

- T1 normalize 正常响应；
- T0 knowledge ingest 完成并真实调用 T1、T3；
- T1 输出直接被 T3 接收；
- 重复 chunk upsert 幂等；
- authorized 可检索；unknown/restricted 默认过滤；
- 无命中返回空 `chunks`；
- citation 字段完整且可追溯；
- T1 非法输入返回稳定 `VALIDATION_ERROR`；
- T0 guide/query 消费 T3 citation 成功（T4 使用 Stub）；
- T0/T1/T3 追踪 ID 请求/响应头可复现；
- 停止 T3 后 T0 返回 `DOWNSTREAM_MODULE_ERROR`，禁止无依据生成。

证据目录：

```text
联调证据/2026-08-13-t1-t3-acceptance/
```

其中请求、响应、错误、日志和 `test-results.txt` 已按目录保存。数据库是运行产物，不建议提交。

## 结论

**T3 MVP：有条件通过。**

T3 的代码契约、自动化测试、真实 HTTP 边界、授权过滤、无命中、幂等、citation 和追踪行为已通过。2026-08-13 的 T1/T3 专项脚本对 T2 使用临时 Stub；截至 2026-08-15，真实 T2 MVP 已接入 T0 并完成 T0/T1/T2/T3 HTTP 集成收口，最新证据见 `联调证据/2026-08-15-t2-integration-closure/`。T4/T6 真实模型质量、专业资料逐条复核、授权确认、公开发布审批、生产部署和召回率评测尚未完成。当前不能将本报告解释为真实模型质量或生产级检索验收。
