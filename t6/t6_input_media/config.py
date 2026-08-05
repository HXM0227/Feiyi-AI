from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "mock"
    host: str = "0.0.0.0"
    port: int = 8106
    contract_version: str = "1.0.0"

    dashscope_api_key: str = ""
    dashscope_workspace_id: str = ""
    dashscope_base_http_api_url: str = (
        "https://dashscope.aliyuncs.com/api/v1"
    )
    asr_model: str = "qwen3-asr-flash"
    tts_model: str = "qwen3-tts-flash"
    tts_voice: str = "Cherry"
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        mode = os.getenv("T6_MODE", "mock").strip().lower()
        if mode not in {"mock", "dashscope"}:
            raise ValueError("T6_MODE must be 'mock' or 'dashscope'")

        workspace_id = os.getenv("T6_WORKSPACE_ID", "").strip()
        default_base_url = (
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1"
            if workspace_id
            else "https://dashscope.aliyuncs.com/api/v1"
        )

        settings = cls(
            mode=mode,
            host=os.getenv("T6_HOST", "0.0.0.0"),
            port=int(os.getenv("T6_PORT", "8106")),
            contract_version=os.getenv("T6_CONTRACT_VERSION", "1.0.0"),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
            dashscope_workspace_id=workspace_id,
            dashscope_base_http_api_url=os.getenv(
                "T6_DASHSCOPE_BASE_HTTP_API_URL",
                default_base_url,
            ).rstrip("/"),
            asr_model=os.getenv("T6_ASR_MODEL", "qwen3-asr-flash"),
            tts_model=os.getenv("T6_TTS_MODEL", "qwen3-tts-flash"),
            tts_voice=os.getenv("T6_TTS_VOICE", "Cherry").strip() or "Cherry",
            max_audio_bytes=int(
                os.getenv("T6_MAX_AUDIO_BYTES", str(10 * 1024 * 1024))
            ),
            max_audio_seconds=int(
                os.getenv("T6_MAX_AUDIO_SECONDS", "300")
            ),
        )

        if settings.mode == "dashscope" and not settings.dashscope_api_key:
            raise ValueError(
                "T6_MODE=dashscope requires DASHSCOPE_API_KEY"
            )

        return settings
