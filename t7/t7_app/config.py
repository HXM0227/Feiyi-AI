from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True, slots=True)
class Settings:
    t0_base_url: str = "http://127.0.0.1:8000"
    t0_api_key: str = ""
    admin_token: str = ""
    request_timeout_seconds: float = 20.0
    database_path: Path = Path("data/t7.db")
    upload_dir: Path = Path("data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    public_base_url: str = ""
    app_name: str = "非遗 AI 智能导览"
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            t0_base_url=os.getenv("T7_T0_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            t0_api_key=os.getenv("T7_T0_API_KEY", ""),
            admin_token=os.getenv("T7_ADMIN_TOKEN", ""),
            request_timeout_seconds=float(os.getenv("T7_REQUEST_TIMEOUT_SECONDS", "20")),
            database_path=Path(os.getenv("T7_DATABASE_PATH", "data/t7.db")),
            upload_dir=Path(os.getenv("T7_UPLOAD_DIR", "data/uploads")),
            max_upload_bytes=_int_env("T7_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
            public_base_url=os.getenv("T7_PUBLIC_BASE_URL", "").rstrip("/"),
            app_name=os.getenv("T7_APP_NAME", "非遗 AI 智能导览"),
            environment=os.getenv("T7_ENVIRONMENT", "development"),
        )
