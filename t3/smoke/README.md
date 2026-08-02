# T3 真实 HTTP 冒烟测试

启动 Uvicorn 后执行：

```powershell
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_smoke.py --base-url http://127.0.0.1:8103 --output .\t3\smoke\latest.json
```

覆盖健康检查、就绪检查、T1 风格 records 入库、授权过滤、引用字段和请求 ID 响应头。

T0→T1→T3 联调：

```powershell
& "..\.venv\Scripts\python.exe" .\t3\smoke\run_t0_t1_t3_http.py
```
