from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "policies.json"


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8105
    contract_version: str = "1.0.0"
    policy_path: Path = DEFAULT_POLICY_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            host=os.getenv("T5_HOST", "0.0.0.0"),
            port=int(os.getenv("T5_PORT", "8105")),
            contract_version=os.getenv("T5_CONTRACT_VERSION", "1.0.0"),
            policy_path=Path(os.getenv("T5_POLICY_PATH", str(DEFAULT_POLICY_PATH))),
        )
