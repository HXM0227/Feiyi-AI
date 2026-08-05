# T6 输入规范化与语音合成

T6 为 T0 导览主链路提供两项能力：将文本、展品 ID 或媒体引用转换为可检索的 `query`，以及在请求音频时返回与 T0 `AudioAsset` 契约兼容的音频资产引用。

当前交付是严格的离线 MVP：文本使用规则语言检测；图片和音频只返回明确标识的占位查询；语音合成返回确定性的 `mock://` 占位 URL。未接入真实 ASR、图像识别、TTS、对象存储或外部模型，不能将该版本表述为真实媒体识别或语音质量已验收。

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
