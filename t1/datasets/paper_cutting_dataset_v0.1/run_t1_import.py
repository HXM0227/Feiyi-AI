from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
REQUEST_PATH = HERE / "paper-cutting-normalize-request.json"
RESPONSE_PATH = HERE / "paper-cutting-normalize-response.json"
LEDGER_PATH = HERE / "paper-cutting-source-ledger.json"
DB_PATH = HERE / "paper-cutting-t1.db"

if DB_PATH.exists():
    DB_PATH.unlink()

os.environ["T1_DB_PATH"] = str(DB_PATH)
os.environ["T1_API_TOKEN"] = ""

os.chdir(WORKSPACE)
sys.path.insert(0, str(WORKSPACE))

from t1.t1_service.api import create_app  # noqa: E402


def main() -> None:
    payload = json.loads(REQUEST_PATH.read_text(encoding="utf-8-sig"))
    if payload.get("publish") is not True:
        raise RuntimeError("当前可用版资料必须保持 publish=true")
    if any(doc.get("authorization_status") != "authorized" for doc in payload["documents"]):
        raise RuntimeError("当前可用版资料的 authorization_status 必须为 authorized")

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/v1/documents/normalize",
            json=payload,
            headers={
                "X-Trace-ID": "paper-cutting-import-20260816",
                "X-Request-ID": "paper-cutting-v1.0",
            },
        )
        response.raise_for_status()
        result = response.json()
        RESPONSE_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        ledger_response = client.get("/v1/sources")
        ledger_response.raise_for_status()
        ledger_payload = ledger_response.json()
        LEDGER_PATH.write_text(
            json.dumps(ledger_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    expected = {doc["source_id"] for doc in payload["documents"]}
    actual = {record["source_id"] for record in result["records"]}
    if result["rejected"]:
        raise RuntimeError(f"存在被拒绝资料: {result['rejected']}")
    if actual != expected:
        raise RuntimeError(f"导入记录不完整，expected={expected}, actual={actual}")
    if result["warnings"]:
        raise RuntimeError(f"authorized 资料不应产生授权警告: {result['warnings']}")
    if any(record.get("authorization_status") != "authorized" for record in result["records"]):
        raise RuntimeError("T1 输出未完整保留 authorized 状态")

    print(f"Imported {len(result['records'])} records")
    print(f"Rejected {len(result['rejected'])} records")
    print(f"Warnings {len(result['warnings'])}")
    print(f"Response: {RESPONSE_PATH}")
    print(f"Ledger: {LEDGER_PATH}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
