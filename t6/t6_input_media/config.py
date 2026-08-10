from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
    vision_model: str = "qwen3.6-flash"
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 300
    ffprobe_path: str = "ffprobe"
    max_image_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 16_000_000
    media_allowed_hosts: tuple[str, ...] = ()
    tts_provider_allowed_hosts: tuple[str, ...] = (
        "dashscope-result-bj.oss-cn-beijing.aliyuncs.com",
    )
    media_download_timeout_seconds: float = 15.0
    storage_backend: str = "local"
    media_dir: Path = Path("data/media")
    public_base_url: str = "http://127.0.0.1:8106"
    media_retention_hours: int = 24

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        mode = os.getenv("T6_MODE", "mock").strip().lower()
        if mode not in {"mock", "dashscope"}:
            raise ValueError("T6_MODE must be 'mock' or 'dashscope'")

        storage_backend = os.getenv("T6_STORAGE_BACKEND", "local").strip().lower()
        if storage_backend != "local":
            raise ValueError("T6_STORAGE_BACKEND 当前仅支持 local")

        allowed_hosts = tuple(
            item.strip().lower()
            for item in os.getenv("T6_MEDIA_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        )
        tts_provider_allowed_hosts = tuple(
            item.strip().lower()
            for item in os.getenv(
                "T6_TTS_PROVIDER_ALLOWED_HOSTS",
                "dashscope-result-bj.oss-cn-beijing.aliyuncs.com",
            ).split(",")
            if item.strip()
        )

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
            vision_model=os.getenv("T6_VISION_MODEL", "qwen3.6-flash").strip()
            or "qwen3.6-flash",
            max_audio_bytes=int(
                os.getenv("T6_MAX_AUDIO_BYTES", str(10 * 1024 * 1024))
            ),
            max_audio_seconds=int(
                os.getenv("T6_MAX_AUDIO_SECONDS", "300")
            ),
            ffprobe_path=os.getenv("T6_FFPROBE_PATH", "ffprobe").strip()
            or "ffprobe",
            max_image_bytes=int(
                os.getenv("T6_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))
            ),
            max_image_pixels=int(
                os.getenv("T6_MAX_IMAGE_PIXELS", "16000000")
            ),
            media_allowed_hosts=allowed_hosts,
            tts_provider_allowed_hosts=tts_provider_allowed_hosts,
            media_download_timeout_seconds=float(
                os.getenv("T6_MEDIA_DOWNLOAD_TIMEOUT_SECONDS", "15")
            ),
            storage_backend=storage_backend,
            media_dir=Path(os.getenv("T6_MEDIA_DIR", "data/media")),
            public_base_url=os.getenv(
                "T6_PUBLIC_BASE_URL", "http://127.0.0.1:8106"
            ).rstrip("/"),
            media_retention_hours=int(
                os.getenv("T6_MEDIA_RETENTION_HOURS", "24")
            ),
        )

        if settings.mode == "dashscope" and not settings.dashscope_api_key:
            raise ValueError(
                "T6_MODE=dashscope requires DASHSCOPE_API_KEY"
            )

        if settings.max_audio_bytes <= 0 or settings.max_image_bytes <= 0:
            raise ValueError("T6 媒体大小上限必须为正数")
        if settings.max_audio_seconds <= 0 or settings.max_image_pixels <= 0:
            raise ValueError("T6 媒体时长和像素上限必须为正数")
        if settings.media_retention_hours <= 0:
            raise ValueError("T6_MEDIA_RETENTION_HOURS 必须为正数")

        return settings
