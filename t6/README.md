# T6 输入规范化与语音合成

T6 为 T0 导览主链路提供两项能力：将文本、展品 ID 或媒体引用转换为可检索的 `query`，以及在请求音频时返回与 T0 `AudioAsset` 契约兼容的音频资产引用。

当前交付同时支持离线 Mock 和百炼真实模式。Mock 用于无密钥的契约测试；`T6_MODE=dashscope` 时可调用短音频 ASR、图片理解和 TTS。真实图片/音频输入必须是白名单内的公开 HTTPS URL；TTS 返回的百炼临时 WAV 会被下载到本地开发媒体目录，再由 T6 返回可播放 URL。

本地媒体目录不是生产对象存储：它不提供多机共享、权限控制、病毒扫描或长期保存。真实 T7 上传媒体联调需要 T7 的公网 HTTPS 地址或 OSS 接入。

## 启动

```powershell
cd t6
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn t6_input_media.api:app --host 0.0.0.0 --port 8106
```

默认 `T6_MODE=mock`。接口文档位于 `http://127.0.0.1:8106/docs`。

## 真实模式

在 `.env` 中设置 `T6_MODE=dashscope`、`DASHSCOPE_API_KEY` 和模型工作区配置。还必须设置 `T6_MEDIA_ALLOWED_HOSTS`，例如团队批准的 OSS、T7 公网域名或公开测试样例域名。空白名单会拒绝真实图片和音频输入。

媒体限制：音频接受 WAV、MP3、M4A、Ogg、WebM，默认不超过 10 MB / 300 秒；图片仅接受 JPEG、PNG、WebP，默认不超过 10 MB / 1600 万像素。重定向、内网地址和非 HTTPS 地址会被拒绝。WebM 仅接受不含视频轨的 Opus/Vorbis 音频，须安装 FFmpeg 并让 `T6_FFPROBE_PATH` 指向可执行的 `ffprobe`；可用 `ffprobe -version` 验证。缺少该依赖时，WebM 请求返回 `503`。

TTS 最多接受 600 个字符。真实模式会把百炼临时 WAV 转存到 `T6_MEDIA_DIR`，并从 `${T6_PUBLIC_BASE_URL}/media/audio/` 返回播放地址；默认文件保留 24 小时。

## 验证

```powershell
python -m unittest discover -s tests -v
```

## T0 联调

在 T0 环境中配置：

```ini
T0_MODE=http
T6_BASE_URL=http://127.0.0.1:8106
```

T0 调用 `POST /v1/input/normalize` 后将 `query` 交给 T3 检索；当 `options.return_audio=true` 时，T0 再调用 `POST /v1/audio/synthesize`。详细字段见 [接口说明](docs/interface.md)。

T6 分支中的 `smoke/run_t0_text_tts_http.py` 用于人工验证已启动的 T0、T3、T4 和 T6 服务的文本+TTS HTTP 链路。
