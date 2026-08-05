# T6 接口契约（MVP）

服务默认地址为 `http://127.0.0.1:8106`。所有请求和响应均为 JSON。服务接受 T0 透传的 `X-Trace-ID`、`X-Request-ID`、`Authorization` 请求头；MVP 不自行鉴权，也不回显这些头。

## `POST /v1/input/normalize`

T0 调用时的请求：

```json
{
  "input": {
    "type": "text",
    "text": "请介绍剪纸"
  },
  "source_language": "auto"
}
```

`input.type` 仅支持 `text`、`audio`、`image`、`exhibit_id`。文本、媒体 URL、展品 ID 分别使用 `text`、`media_url`、`exhibit_id` 字段。`source_language` 支持 `auto`、`zh` / `zh-CN`、`en` / `en-US` / `en-GB`。

响应始终包含 T0 所需的非空 `query`、`detected_language` 和 0–1 的 `confidence`：

```json
{
  "query": "请介绍剪纸",
  "detected_language": "zh-CN",
  "confidence": 0.99
}
```

MVP 仅对文本作规则语言检测。音频和图片在未显式指定源语言时返回 `detected_language: "unknown"` 和 `confidence: 0.0`，并生成占位检索查询；它们不代表已完成 ASR 或图像识别。

## `POST /v1/audio/synthesize`

请求：

```json
{
  "text": "有据讲解文本",
  "language": "zh-CN",
  "voice": "default"
}
```

响应严格只含 T0 `AudioAsset` 兼容字段：

```json
{
  "url": "mock://audio/0123456789abcdef.mp3",
  "mime_type": "audio/mpeg",
  "voice": "default"
}
```

`mock://` 资源是确定性占位符，不能作为可播放音频或真实 TTS 验收证据。

## 健康检查

- `GET /healthz`：服务进程存活。
- `GET /readyz`：当前 Mock 模式可提供离线契约服务。
