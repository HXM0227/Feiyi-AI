from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "mock"
    host: str = "0.0.0.0"
    port: int = 8104
    contract_version: str = "1.0.0"
    terminology_path: Path = Path("data/terminology_zh_en.json")
    audit_dir: Path = Path("runtime/audit")
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_timeout_seconds: float = 20.0
    qwen_temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        mode = os.getenv("T4_MODE", "mock").strip().lower()
        if mode not in {"mock", "qwen"}:
            raise ValueError("T4_MODE must be 'mock' or 'qwen'")
        return cls(
            mode=mode,
            host=os.getenv("T4_HOST", "0.0.0.0"),
            port=int(os.getenv("T4_PORT", "8104")),
            contract_version=os.getenv("T4_CONTRACT_VERSION", "1.0.0"),
            terminology_path=Path(os.getenv("T4_TERMINOLOGY_PATH", "data/terminology_zh_en.json")),
            audit_dir=Path(os.getenv("T4_AUDIT_DIR", "runtime/audit")),
            qwen_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            qwen_base_url=os.getenv("T4_QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/"),
            qwen_model=os.getenv("T4_QWEN_MODEL", "qwen-plus"),
            qwen_timeout_seconds=float(os.getenv("T4_QWEN_TIMEOUT_SECONDS", "20")),
            qwen_temperature=float(os.getenv("T4_QWEN_TEMPERATURE", "0.2")),
        )
