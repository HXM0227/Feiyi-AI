from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8103
    contract_version: str = "1.0.0"
    db_path: str = "./data/t3.db"
    api_token: str = ""
    max_top_k: int = 20
    max_excerpt_chars: int = 1000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("T3_HOST", "127.0.0.1"),
            port=int(os.getenv("T3_PORT", "8103")),
            contract_version=os.getenv("T3_CONTRACT_VERSION", "1.0.0"),
            db_path=os.getenv("T3_DB_PATH", "./data/t3.db"),
            api_token=os.getenv("T3_API_TOKEN", ""),
            max_top_k=int(os.getenv("T3_MAX_TOP_K", "20")),
            max_excerpt_chars=int(os.getenv("T3_MAX_EXCERPT_CHARS", "1000")),
        )

    def ensure_db_parent(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
