# T8 多语种传播内容生成

T8 将 T0 提供的 T3 可引用资料加工为渠道传播草稿。它不自行检索、不保存或发布内容，也不能创造引用；T7 通过 T0 调用 T8，并将结果保存为待审核草稿。

## MVP 范围

- 目标语言：`zh-CN`、`en`。
- 渠道：`short_video`、`poster`、`social`、`event_intro`。
- 模式：离线确定性 `mock`，以及可选千问 `qwen`。
- 质量门：非空、Unicode 字符长度、引用白名单、目标语言（千问模式）和强制人工审核。
- 安全降级：千问调用或输出校验失败时，返回受当前 context 约束的确定性草稿，并设置 `fallback_used=true`。

Mock 适合契约、渠道结构和链路测试，不代表翻译或传播质量已验收。若 context 语言与目标语言不同，Mock 不会伪装成翻译器或把原文硬塞进目标语言文案，而会返回目标语言的“需要人工翻译与审核”提示及引用。自然的跨语言改写需要千问模式和人工审核。

## 环境与启动

PowerShell：

```powershell
cd t8
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn t8_content_generation.api:app --host 0.0.0.0 --port 8108
```

默认 `T8_MODE=mock`，不需要网络或模型密钥。接口文档位于 `http://127.0.0.1:8108/docs`。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖四种渠道、中英文、最短长度、引用去重、非法输入、追踪头、强制审核以及千问无引用、未知引用、错误语言、超长和调用失败的降级。

## 千问模式

仅在未提交的 `t8/.env` 写入密钥：

```ini
T8_MODE=qwen
DASHSCOPE_API_KEY=你的千问密钥
T8_QWEN_MODEL=qwen-plus
```

真实成功必须同时满足 `generator_mode=qwen`、`fallback_used=false`、引用和长度校验通过。`fallback_mock` 只能说明服务安全降级成功，不能算真实模型质量验收。

## T0 联调

启动 T8 后，T0 应显式设置：

```ini
T0_MODE=http
T8_BASE_URL=http://127.0.0.1:8108
```

也可以保持 T0 其余模块为 Mock，仅将 T8 换成真实 HTTP 客户端：

```powershell
python smoke/run_t0_t8_http.py
```

当前 T0 会将 T3 返回的全部 citations 交给 T7，而不是按 T8 的 `used_citation_ids` 过滤。T8 已准确返回实际使用引用；T0 侧调整需要由其负责人另行处理。

## 运行产物

审计记录写入 `runtime/audit/content_generation_audit.jsonl`，只保存主题、渠道、运行模式、来源 ID 和引用 ID，不复制完整 context。`.env`、`.venv`、`runtime/` 和日志均被忽略。
