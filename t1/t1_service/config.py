from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8101
    contract_version: str = "1.0.0"
    db_path: str = "./data/t1.db"
    max_chunk_chars: int = 800
    chunk_overlap: int = 100
    api_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        max_chars = int(os.getenv("T1_MAX_CHUNK_CHARS", "800"))
        overlap = int(os.getenv("T1_CHUNK_OVERLAP", "100"))
        if max_chars < 1:
            raise ValueError("T1_MAX_CHUNK_CHARS must be positive")
        if overlap < 0 or overlap >= max_chars:
            raise ValueError("T1_CHUNK_OVERLAP must be >= 0 and smaller than max chunk size")
        return cls(
            host=os.getenv("T1_HOST", "127.0.0.1"),
            port=int(os.getenv("T1_PORT", "8101")),
            contract_version=os.getenv("T1_CONTRACT_VERSION", "1.0.0"),
            db_path=os.getenv("T1_DB_PATH", "./data/t1.db"),
            max_chunk_chars=max_chars,
            chunk_overlap=overlap,
            api_token=os.getenv("T1_API_TOKEN", ""),
        )

    def ensure_db_parent(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
