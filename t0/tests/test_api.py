from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from t0_orchestrator.api import create_app
from t0_orchestrator.config import Settings


async def asgi_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    app = create_app(Settings(mode="mock"))
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else b""
    request_sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    raw_headers = {"content-type": "application/json", **(headers or {})}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in raw_headers.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }
    await app(scope, receive, send)
    start = next(item for item in messages if item["type"] == "http.response.start")
    response_body = b"".join(
        item.get("body", b"")
        for item in messages
        if item["type"] == "http.response.body"
    )
    return start["status"], json.loads(response_body)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_healthz(self) -> None:
        status, body = await asgi_request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

    async def test_guide_query_accepts_request_id_header(self) -> None:
        status, body = await asgi_request(
            "POST",
            "/v1/guide/query",
            {
                "session_id": "s-api-001",
                "target_language": "en",
                "input": {"type": "text", "text": "请介绍这项非遗"},
            },
            {"x-request-id": "request-from-t7"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["request_id"], "request-from-t7")
        self.assertGreaterEqual(len(body["citations"]), 1)

    async def test_validation_error_uses_unified_contract(self) -> None:
        status, body = await asgi_request(
            "POST",
            "/v1/guide/query",
            {"session_id": "s-api-002"},
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")
        self.assertFalse(body["retryable"])
        self.assertIn("errors", body["details"])


if __name__ == "__main__":
    unittest.main()
