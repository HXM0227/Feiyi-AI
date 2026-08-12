"""Manual smoke test for an already-running T0 + T3 + T4 + T6 HTTP stack.

Start T0 in HTTP mode, T3 with a writable SQLite path, T4 in mock mode, and T6 in
DashScope mode before running this script. It seeds one authorized T3 record and
then verifies that T0 returns a source-grounded answer and an audio asset.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


T0_BASE_URL = os.getenv("T0_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
T3_BASE_URL = os.getenv("T3_BASE_URL", "http://127.0.0.1:8103").rstrip("/")


def request_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError(f"响应不是 JSON 对象：{url}")
    return result


def main() -> int:
    marker = uuid.uuid4().hex[:8]
    query = f"请介绍剪纸工艺 {marker}"
    upsert = request_json(
        f"{T3_BASE_URL}/v1/index/upsert",
        {
            "records": [
                {
                    "source_id": f"SMOKE-{marker}",
                    "source_uri": "https://example.org/t6-smoke",
                    "title": "T6 联调剪纸资料",
                    "media_type": "text",
                    "authorization_status": "authorized",
                    "chunks": [
                        {
                            "chunk_id": f"SMOKE-{marker}-001",
                            "text": f"剪纸工艺 {marker} 以剪刀或刻刀在纸上制作镂空纹样。",
                            "sequence": 1,
                            "language": "zh-CN",
                        }
                    ],
                }
            ],
            "publish": True,
        },
    )
    if not upsert.get("accepted_count"):
        raise RuntimeError(f"T3 未接受测试资料：{upsert}")

    result = request_json(
        f"{T0_BASE_URL}/v1/guide/query",
        {
            "session_id": f"t6-smoke-{marker}",
            "input": {"type": "text", "text": query},
            "source_language": "zh-CN",
            "target_language": "zh-CN",
            "options": {"return_audio": True, "debug": True},
        },
    )
    audio = result.get("audio")
    if not result.get("answer") or not result.get("citations") or not isinstance(audio, dict):
        raise RuntimeError(f"T0 文本+TTS 联调失败：{result}")
    audio_url = audio.get("url")
    if not isinstance(audio_url, str) or not audio_url.startswith(("http://", "https://")):
        raise RuntimeError(f"T6 未返回可访问音频 URL：{audio}")
    with urlopen(audio_url, timeout=15) as response:
        if not response.read(12).startswith(b"RIFF"):
            raise RuntimeError("T6 返回的音频不是预期 WAV 数据")
    print(json.dumps({"status": "ok", "audio_url": audio_url}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
