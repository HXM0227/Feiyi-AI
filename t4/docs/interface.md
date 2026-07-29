# T4 与 T0 接口说明

T0 在导览主链路中调用 `POST http://127.0.0.1:8104/v1/generate`，并透传 `X-Trace-ID`、`X-Request-ID`、`Authorization`。T4 当前不依赖这些请求头，但不拒绝它们。

## 请求

字段与 T0 第一阶段的 `orchestrator.py` 调用完全对应：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `query` | 是 | T6 已规范化的用户问题 |
| `detected_language` | 是 | T6 的检测结果，`auto` 时由 T4 轻量检测 |
| `target_language` | 是 | `zh-CN` 或 `en` |
| `audience` | 是 | T0 透传的受众画像 |
| `context` | 是 | T3 返回的可引用片段；不能为空 |
| `graph_context` | 否 | T2 约束和关系信息 |
| `adaptation` | 否 | T5 的画像与叙事指令 |
| `requirements` | 否 | 引用格式、上下文约束与事实/类比边界 |

完整请求见 `examples/requests/generate-paper-cutting-en.json`。

## 响应

`answer` 和 `used_citation_ids` 是 T0 当前消费的字段。其余字段帮助联调、审计和质量复核。

```json
{
  "answer": "... [CIT-001]",
  "used_citation_ids": ["CIT-001"],
  "detected_language": "zh-CN",
  "target_language": "en",
  "terminology_check": {"passed": true, "applicable_terms": [], "missing_terms": []},
  "prompt_version": "t4-grounded-bilingual-1.0",
  "generator_mode": "mock",
  "warnings": [],
  "fallback_used": false
}
```

无上下文、未知目标语种和不合格输入均返回 HTTP 422；千问模式的模型调用、响应、引用或术语校验失败时则返回带 `fallback_used: true` 的受限 Mock 结果。
