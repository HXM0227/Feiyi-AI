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

Mock 模式仅对文本作规则语言检测。DashScope 模式下，音频会先通过 URL、域名白名单、MIME、文件大小和时长校验，再调用 ASR；图片会通过同类 URL、MIME、大小和像素校验，再调用视觉模型并返回其结构化检索查询。图片模型只生成可检索线索，不保证识别出准确展品名称或历史事实。

真实媒体 URL 必须是白名单内的 HTTPS 地址，且不允许重定向。支持音频 WAV、MP3、M4A、Ogg、WebM；支持图片 JPEG、PNG、WebP。WebM 必须是仅含 Opus/Vorbis 音频轨的真实 WebM 容器，T6 使用 `T6_FFPROBE_PATH` 指定的 `ffprobe` 校验其内容和时长。超出大小限制返回 `413`，格式、地址、时长或像素不合格返回 `422`，缺少或无法执行 WebM 校验依赖返回 `503`，模型调用失败返回 `502`。

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

Mock 模式中，`mock://` 资源是确定性占位符，不能作为可播放音频或真实 TTS 验收证据。

DashScope 模式中，T6 会下载并校验百炼临时 WAV，再将其保存到本地开发媒体目录，响应 URL 为 `${T6_PUBLIC_BASE_URL}/media/audio/<id>.wav`。响应字段不变，仍严格只包含 `url`、`mime_type`、`voice`。本地媒体目录会按 `T6_MEDIA_RETENTION_HOURS` 清理，不能作为生产对象存储。

## 健康检查

- `GET /healthz`：服务进程存活。
- `GET /readyz`：当前 Mock 模式可提供离线契约服务。
