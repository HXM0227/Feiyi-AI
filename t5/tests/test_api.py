from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from t5_cultural_adaptation.api import create_app
from t5_cultural_adaptation.config import DEFAULT_POLICY_PATH, Settings


async def request_asgi(
    app: Any,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
    sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers = [(b"content-type", b"application/json"), *(extra_headers or [])]
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
            "root_path": "",
        },
        receive,
        send,
    )
    status = next(item["status"] for item in messages if item["type"] == "http.response.start")
    content = b"".join(
        item.get("body", b"") for item in messages if item["type"] == "http.response.body"
    )
    return status, json.loads(content)


def t0_payload() -> dict[str, Any]:
    return {
        "query": "请介绍剪纸",
        "target_language": "en",
        "audience": {
            "region": "global",
            "age_band": "adult",
            "knowledge_level": "general",
            "style": "educational",
        },
        "graph_context": {},
        "retrieval_context": [
            {
                "citation_id": "CIT-001",
                "source_id": "SRC-001",
                "title": "剪纸资料",
                "section": "工艺",
                "uri": "https://example.org/source/1",
                "excerpt": "剪纸以纸张为主要材料。",
                "score": 0.95,
            }
        ],
    }


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = create_app(Settings(policy_path=DEFAULT_POLICY_PATH))

    async def test_health_and_ready(self) -> None:
        status, body = await request_asgi(self.app, "GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["policy_version"], "t5-cultural-policy-1.0.0")
        status, body = await request_asgi(self.app, "GET", "/readyz")
        self.assertEqual((status, body["status"]), (200, "ok"))

    async def test_exact_t0_request_and_headers_are_accepted(self) -> None:
        status, body = await request_asgi(
            self.app,
            "POST",
            "/v1/adapt",
            t0_payload(),
            [
                (b"x-trace-id", b"trace-t5-test"),
                (b"x-request-id", b"request-t5-test"),
                (b"authorization", b"Bearer test-token"),
            ],
        )
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"policy_version", "instructions", "blocked_terms"})

    async def test_empty_context_is_rejected(self) -> None:
        payload = t0_payload()
        payload["retrieval_context"] = []
        status, body = await request_asgi(self.app, "POST", "/v1/adapt", payload)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_unknown_language_is_rejected(self) -> None:
        payload = t0_payload()
        payload["target_language"] = "ja"
        status, body = await request_asgi(self.app, "POST", "/v1/adapt", payload)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_t4_language_alias_is_canonicalized(self) -> None:
        payload = t0_payload()
        payload["target_language"] = "en-us"
        status, body = await request_asgi(self.app, "POST", "/v1/adapt", payload)
        self.assertEqual(status, 200)
        self.assertIn("uncivilized people", body["blocked_terms"])

    async def test_invalid_audience_enum_is_rejected(self) -> None:
        payload = t0_payload()
        payload["audience"]["age_band"] = "preschool"
        status, body = await request_asgi(self.app, "POST", "/v1/adapt", payload)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")

    async def test_extra_field_is_rejected(self) -> None:
        payload = t0_payload()
        payload["unexpected"] = True
        status, body = await request_asgi(self.app, "POST", "/v1/adapt", payload)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
