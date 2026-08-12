# T8 接口契约

## `POST /v1/content/generate`

T0 在完成 T3 检索后调用本接口。请求和响应均为 JSON；服务兼容并回传 `X-Trace-ID`、`X-Request-ID`，接受 T0 可选的 `Authorization: Bearer ...` 请求头但不在 T8 重复实施入口鉴权。

### 请求

| 字段 | 必填 | 约束 |
|---|---:|---|
| `topic` | 是 | 1—500 字符 |
| `target_language` | 否 | `zh-CN` 或 `en`，兼容常用别名 |
| `platform` | 是 | `short_video`、`poster`、`social`、`event_intro` |
| `audience` | 否 | 与 T0 `AudienceProfile` 一致 |
| `max_length` | 否 | 50—5000，默认 500 |
| `context` | 是 | 1—20 个 T3 引用片段 |
| `requirements` | 否 | `human_review` 与 `preserve_citations` 只能为 `true` |

`max_length` 按最终 `content` 的 Python/Unicode 字符数计算，包括空格、标点、换行和 `[citation_id]`。这不是英文单词数或 UTF-8 字节数。

`context` 项与 T3/T0 当前契约一致：`citation_id`、`source_id`、`title`、`excerpt` 必填；`section`、`uri`、`score` 可选。`citation_id` 仅允许字母、数字、下划线和连字符，以避免引用标记歧义。

请求示例见 `examples/requests/`。

### 响应

```json
{
  "content": "Discover Chinese Paper Cutting ... [CIT-001]",
  "used_citation_ids": ["CIT-001"],
  "review_required": true,
  "target_language": "en",
  "platform": "social",
  "template_version": "t8-platform-templates-1.0.0",
  "generator_mode": "mock",
  "warnings": [],
  "fallback_used": false,
  "length": 146
}
```

- `used_citation_ids` 按文中首次出现顺序去重，且必须是请求 context ID 的子集。
- `review_required` 始终为 `true`；T8 无权批准或发布内容。
- `generator_mode` 为 `mock`、`qwen` 或 `fallback_mock`。
- `length` 使用与 `max_length` 相同的 Unicode 字符计算规则。

### 失败与降级

- 请求契约错误返回 HTTP 422、`code=VALIDATION_ERROR`。
- Mock 无法生成合规内容时返回 HTTP 422。
- 千问调用失败、空输出、超长、目标语言错误、无引用或未知引用时安全降级，HTTP 200 返回 `fallback_mock` 和非空 `warnings`。
- Mock 遇到 context 与目标语言不一致时不执行伪翻译，返回目标语言的待人工翻译提示、有效引用和 warning。
- 无 context 时拒绝生成，不构造示例引用。

## 健康检查

- `GET /healthz`：进程存活即返回 200。
- `GET /readyz`：Mock 返回 200；Qwen 模式缺少 `DASHSCOPE_API_KEY` 时返回 503。

T0 当前 `/readyz` 不将 T8 视为导览主链路关键模块，这不影响内容生成接口在调用 T8 失败时整体失败。
