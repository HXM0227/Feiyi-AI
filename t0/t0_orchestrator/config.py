from __future__ import annotations

import os
from dataclasses import dataclass, field


MODULE_IDS = ("T1", "T2", "T3", "T4", "T5", "T6", "T8", "T9")


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "mock"
    api_key: str = ""
    downstream_token: str = ""
    contract_version: str = "1.0.0"
    timeout_seconds: float = 12.0
    retry_count: int = 1
    idempotency_ttl_seconds: int = 600
    module_urls: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("T0_MODE", "mock").strip().lower()
        if mode not in {"mock", "http"}:
            raise ValueError("T0_MODE must be 'mock' or 'http'")
        urls = {
            module_id: os.getenv(
                f"{module_id}_BASE_URL", f"http://127.0.0.1:81{module_id[1:]}"
            ).rstrip("/")
            for module_id in MODULE_IDS
        }
        return cls(
            mode=mode,
            api_key=os.getenv("T0_API_KEY", ""),
            downstream_token=os.getenv("T0_DOWNSTREAM_TOKEN", ""),
            contract_version=os.getenv("T0_CONTRACT_VERSION", "1.0.0"),
            timeout_seconds=_float_env("T0_TIMEOUT_SECONDS", 12.0),
            retry_count=_int_env("T0_RETRY_COUNT", 1),
            idempotency_ttl_seconds=_int_env("T0_IDEMPOTENCY_TTL_SECONDS", 600),
            module_urls=urls,
        )
