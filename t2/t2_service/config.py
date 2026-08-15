from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8102
    contract_version: str = "1.0.0"
    db_path: str = "./data/t2.db"
    api_token: str = ""
    max_records: int = 1000
    max_entities_per_record: int = 1000
    max_relations_per_record: int = 2000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("T2_HOST", "127.0.0.1"),
            port=int(os.getenv("T2_PORT", "8102")),
            contract_version=os.getenv("T2_CONTRACT_VERSION", "1.0.0"),
            db_path=os.getenv("T2_DB_PATH", "./data/t2.db"),
            api_token=os.getenv("T2_API_TOKEN", ""),
            max_records=int(os.getenv("T2_MAX_RECORDS", "1000")),
            max_entities_per_record=int(os.getenv("T2_MAX_ENTITIES_PER_RECORD", "1000")),
            max_relations_per_record=int(os.getenv("T2_MAX_RELATIONS_PER_RECORD", "2000")),
        )

    def ensure_db_parent(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
