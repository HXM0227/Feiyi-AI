from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from t4_multilingual.api import create_app
from t4_multilingual.config import Settings


ROOT = Path(__file__).resolve().parents[1]


async def request_asgi(app, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else b""
    sent, messages = False, []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "headers": [(b"content-type", b"application/json")], "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": ""}, receive, send)
    status = next(item["status"] for item in messages if item["type"] == "http.response.start")
    content = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
    return status, json.loads(content)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def app(self, temp: str):
        return create_app(Settings(mode="mock", terminology_path=ROOT / "data" / "terminology_zh_en.json", audit_dir=Path(temp) / "audit"))

    async def test_health_and_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            app = self.app(temp)
            status, body = await request_asgi(app, "GET", "/healthz")
            self.assertEqual((status, body["status"]), (200, "ok"))
            status, _ = await request_asgi(app, "GET", "/readyz")
            self.assertEqual(status, 200)

    async def test_t0_compatible_request(self) -> None:
        data = json.loads((ROOT / "data" / "sample_context.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            status, body = await request_asgi(self.app(temp), "POST", "/v1/generate", data)
        self.assertEqual(status, 200)
        self.assertIn("answer", body)
        self.assertEqual(body["used_citation_ids"], ["CIT-001", "CIT-002"])

    async def test_empty_context_is_rejected(self) -> None:
        data = json.loads((ROOT / "data" / "sample_context.json").read_text(encoding="utf-8"))
        data["context"] = []
        with tempfile.TemporaryDirectory() as temp:
            status, body = await request_asgi(self.app(temp), "POST", "/v1/generate", data)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_unknown_target_language_is_rejected(self) -> None:
        data = json.loads((ROOT / "data" / "sample_context.json").read_text(encoding="utf-8"))
        data["target_language"] = "ja"
        with tempfile.TemporaryDirectory() as temp:
            status, body = await request_asgi(self.app(temp), "POST", "/v1/generate", data)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
