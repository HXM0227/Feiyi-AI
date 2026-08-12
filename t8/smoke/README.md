# T0 → T8 HTTP 烟雾测试

1. 在 `t8/` 启动 T8：

```powershell
.\.venv\Scripts\python.exe -m uvicorn t8_content_generation.api:app --host 127.0.0.1 --port 8108
```

2. 在另一个终端运行：

```powershell
.\.venv\Scripts\python.exe smoke/run_t0_t8_http.py
```

脚本让 T0 的 T3 保持 Mock，仅把 T8 换成真实 HTTP 服务，以验证 T0 发送的字段、追踪头、长度限制和强制审核标记。它不代表真实 T3、T7 或千问质量已经验收。
