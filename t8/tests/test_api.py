from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from t8_content_generation.api import create_app
from t8_content_generation.config import Settings


ROOT = Path(__file__).resolve().parents[1]


async def asgi_request(
    app,
    method: str,
    target: str,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict]:
    url = urlsplit(target)
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8")
        if body is not None
        else b""
    )
    request_sent = False
    messages: list[dict] = []
    request_headers = {"content-type": "application/json", **(headers or {})}

    async def receive() -> dict:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": url.path,
            "raw_path": url.path.encode(),
            "query_string": url.query.encode(),
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in request_headers.items()
            ],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
            "root_path": "",
        },
        receive,
        send,
    )
    start = next(item for item in messages if item["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode() for key, value in start["headers"]
    }
    raw = b"".join(
        item.get("body", b"")
        for item in messages
        if item["type"] == "http.response.body"
    )
    return start["status"], response_headers, json.loads(raw)


def sample() -> dict:
    return json.loads(
        (ROOT / "examples" / "requests" / "generate-paper-cutting-en.json").read_text(
            encoding="utf-8"
        )
    )


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def app(self, temp: str, *, mode: str = "mock", key: str = ""):
        return create_app(
            Settings(
                mode=mode,
                qwen_api_key=key,
                template_path=ROOT / "data" / "platform_templates.json",
                audit_dir=Path(temp) / "audit",
            )
        )

    async def test_health_and_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            app = self.app(temp)
            status, _, body = await asgi_request(app, "GET", "/healthz")
            self.assertEqual((status, body["status"]), (200, "ok"))
            status, _, body = await asgi_request(app, "GET", "/readyz")
            self.assertEqual((status, body["mode"]), (200, "mock"))

    async def test_qwen_without_key_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            status, _, _ = await asgi_request(
                self.app(temp, mode="qwen"), "GET", "/readyz"
            )
        self.assertEqual(status, 503)

    async def test_t0_compatible_request_and_trace_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            status, headers, body = await asgi_request(
                self.app(temp),
                "POST",
                "/v1/content/generate",
                sample(),
                {"x-trace-id": "trace-t8-001", "x-request-id": "request-t8-001"},
            )
        self.assertEqual(status, 200)
        self.assertTrue(body["content"])
        self.assertEqual(body["used_citation_ids"], ["CIT-001"])
        self.assertTrue(body["review_required"])
        self.assertEqual(headers["x-trace-id"], "trace-t8-001")
        self.assertEqual(headers["x-request-id"], "request-t8-001")

    async def test_empty_context_is_rejected(self) -> None:
        data = sample()
        data["context"] = []
        with tempfile.TemporaryDirectory() as temp:
            status, _, body = await asgi_request(
                self.app(temp), "POST", "/v1/content/generate", data
            )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_unknown_platform_is_rejected(self) -> None:
        data = sample()
        data["platform"] = "unknown"
        with tempfile.TemporaryDirectory() as temp:
            status, _, body = await asgi_request(
                self.app(temp), "POST", "/v1/content/generate", data
            )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_extra_field_is_rejected(self) -> None:
        data = sample()
        data["unapproved_field"] = True
        with tempfile.TemporaryDirectory() as temp:
            status, _, body = await asgi_request(
                self.app(temp), "POST", "/v1/content/generate", data
            )
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
