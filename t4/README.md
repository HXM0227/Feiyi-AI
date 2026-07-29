# T4 多语种理解、翻译与生成

T4 是项目的 P0 语言服务：它消费 T3 的有来源检索片段、T2 的知识约束和 T5 的受众策略，输出中英双语的可引用讲解。它不自行检索知识，也不替代跨文化策略模块。

## 交付内容

- `t4_multilingual/`：FastAPI 服务、Mock/千问生成器、术语和审计逻辑。
- `data/terminology_zh_en.json`：版本化中英术语库。
- `docs/interface.md`：与 T0 的接口契约。
- `examples/`：导览请求、审计示例和回译抽检报告。
- `tests/`：离线单元和 ASGI 接口测试。

## 虚拟环境与启动

PowerShell：

```powershell
cd t4
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn t4_multilingual.api:app --host 0.0.0.0 --port 8104
```

默认 `T4_MODE=mock`，无需模型密钥或网络。服务文档位于 `http://127.0.0.1:8104/docs`。

## 千问模式

仅将真实密钥写到本地、未提交的 `.env`：

```ini
T4_MODE=qwen
DASHSCOPE_API_KEY=你的千问密钥
T4_QWEN_MODEL=qwen-plus
```

T4 使用千问 OpenAI 兼容的 Chat Completions 地址。调用或输出校验失败时，服务会明确标注并退回到受 T3 上下文约束的 Mock 结果，绝不生成无引用内容。

## 验收

```powershell
python -m unittest discover -s tests -v
python scripts/back_translation_check.py
```

回译脚本生成 `examples/back_translation_report.json`，包括原文、目标文本、回译、术语和引用检查及人工复核结论。运行审计记录写入被忽略的 `runtime/audit/generation_audit.jsonl`；仓库保留了一份无密钥的样例记录。

## T0 联调

在 T0 环境中设置：

```ini
T0_MODE=http
T4_BASE_URL=http://127.0.0.1:8104
```

随后用 T0 的导览请求调用主链路。T0 会读取 T4 返回的 `answer` 和 `used_citation_ids`，并以 T3 的原始元数据组装最终引用。
