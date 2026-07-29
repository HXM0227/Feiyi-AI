from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from t7_app.api import create_app
from t7_app.config import Settings
from t7_app.store import ContentStore


class FakeT0Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, path: str) -> dict[str, Any]:
        if path == "/healthz":
            return {"status": "ok"}
        if path == "/v1/capabilities":
            return {
                "contract_version": "1.0.0",
                "mode": "mock",
                "languages": ["zh-CN", "en"],
                "input_types": ["text", "audio", "image", "exhibit_id"],
                "routes": ["guide.query", "content.generate", "feedback"],
            }
        raise AssertionError(path)

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "path": path,
                "payload": payload,
                "request_id": request_id,
                "idempotency_key": idempotency_key,
            }
        )
        if path == "/v1/guide/query":
            return {
                "contract_version": "1.0.0",
                "trace_id": "trace-guide-001",
                "request_id": request_id,
                "session_id": payload["session_id"],
                "answer": "这是带来源的导览回答。",
                "detected_language": "zh-CN",
                "target_language": payload["target_language"],
                "citations": [
                    {
                        "citation_id": "CIT-001",
                        "source_id": "SRC-001",
                        "title": "示例来源",
                    }
                ],
                "audio": None,
                "warnings": [],
                "pipeline": [],
                "created_at": "2026-07-29T00:00:00Z",
            }
        if path == "/v1/feedback":
            return {
                "contract_version": "1.0.0",
                "trace_id": payload["trace_id"],
                "accepted": True,
            }
        if path == "/v1/content/generate":
            return {
                "contract_version": "1.0.0",
                "trace_id": "trace-content-001",
                "request_id": request_id,
                "content": "面向海外受众的非遗传播文案。",
                "target_language": payload["target_language"],
                "platform": payload["platform"],
                "citations": [
                    {
                        "citation_id": "CIT-001",
                        "source_id": "SRC-001",
                        "title": "示例来源",
                    }
                ],
                "review_required": True,
                "warnings": [],
            }
        if path == "/v1/knowledge/ingest":
            return {
                "contract_version": "1.0.0",
                "trace_id": "trace-ingest-001",
                "request_id": request_id,
                "job_id": "job-001",
                "status": "completed",
                "accepted_count": len(payload["documents"]),
                "warnings": [],
            }
        raise AssertionError(path)


async def asgi_request(
    app,
    method: str,
    target: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    url = urlsplit(target)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
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

    raw_headers = dict(headers or {})
    if body is not None:
        raw_headers.setdefault("content-type", "application/json")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": url.path,
        "raw_path": url.path.encode("utf-8"),
        "query_string": url.query.encode("utf-8"),
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
    response_headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], response_headers, response_body


def json_body(raw: bytes) -> dict[str, Any]:
    return json.loads(raw.decode("utf-8"))


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.fake = FakeT0Client()
        self.settings = Settings(
            admin_token="test-admin",
            database_path=root / "t7.db",
            upload_dir=root / "uploads",
        )
        self.app = create_app(
            self.settings,
            t0_client=self.fake,
            store=ContentStore(self.settings.database_path),
        )

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()

    async def test_health_and_readiness(self) -> None:
        status, _, raw = await asgi_request(self.app, "GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json_body(raw)["module"], "T7")
        status, _, raw = await asgi_request(self.app, "GET", "/readyz")
        self.assertEqual(status, 200)
        self.assertTrue(json_body(raw)["ready"])

    async def test_static_visitor_page(self) -> None:
        status, headers, raw = await asgi_request(self.app, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("非遗 AI 智能导览", raw.decode("utf-8"))

    async def test_config_uses_t0_capabilities(self) -> None:
        status, _, raw = await asgi_request(self.app, "GET", "/api/config")
        body = json_body(raw)
        self.assertEqual(status, 200)
        self.assertTrue(body["t0_available"])
        self.assertIn("en", body["capabilities"]["languages"])

    async def test_guide_query_proxies_request_and_idempotency(self) -> None:
        request = {
            "session_id": "session-001",
            "target_language": "en",
            "input": {"type": "text", "text": "请介绍这项工艺"},
        }
        status, _, raw = await asgi_request(
            self.app,
            "POST",
            "/api/guide/query",
            request,
            {"x-request-id": "request-001", "idempotency-key": "retry-001"},
        )
        body = json_body(raw)
        self.assertEqual(status, 200)
        self.assertEqual(body["trace_id"], "trace-guide-001")
        self.assertEqual(self.fake.calls[-1]["request_id"], "request-001")
        self.assertEqual(self.fake.calls[-1]["idempotency_key"], "retry-001")

    async def test_validation_error_is_stable(self) -> None:
        status, _, raw = await asgi_request(
            self.app,
            "POST",
            "/api/guide/query",
            {"session_id": "session-002"},
        )
        body = json_body(raw)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")
        self.assertIn("errors", body["details"])

    async def test_admin_requires_token(self) -> None:
        status, _, raw = await asgi_request(
            self.app, "GET", "/api/admin/content"
        )
        self.assertEqual(status, 401)
        self.assertIn("令牌", json_body(raw)["detail"])

    async def test_content_generation_and_review_workflow(self) -> None:
        headers = {"x-admin-token": "test-admin"}
        request = {
            "topic": "传统工艺的海外社媒介绍",
            "target_language": "en",
            "platform": "social",
        }
        status, _, raw = await asgi_request(
            self.app,
            "POST",
            "/api/admin/content/generate",
            request,
            headers,
        )
        item = json_body(raw)
        self.assertEqual(status, 200)
        self.assertEqual(item["status"], "draft")
        content_id = item["id"]

        for next_status in ("in_review", "approved", "published"):
            status, _, raw = await asgi_request(
                self.app,
                "PATCH",
                f"/api/admin/content/{content_id}",
                {"status": next_status},
                headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json_body(raw)["status"], next_status)

        status, _, raw = await asgi_request(
            self.app, "GET", "/api/content/published"
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(json_body(raw)["items"]), 1)

    async def test_invalid_content_transition_returns_conflict(self) -> None:
        headers = {"x-admin-token": "test-admin"}
        status, _, raw = await asgi_request(
            self.app,
            "POST",
            "/api/admin/content/generate",
            {
                "topic": "测试主题",
                "target_language": "zh-CN",
                "platform": "poster",
            },
            headers,
        )
        content_id = json_body(raw)["id"]
        status, _, raw = await asgi_request(
            self.app,
            "PATCH",
            f"/api/admin/content/{content_id}",
            {"status": "published"},
            headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(json_body(raw)["code"], "CONTENT_WORKFLOW_CONFLICT")

    async def test_knowledge_ingest_proxies_to_t0(self) -> None:
        status, _, raw = await asgi_request(
            self.app,
            "POST",
            "/api/admin/knowledge/ingest",
            {
                "documents": [
                    {
                        "source_id": "SRC-001",
                        "source_uri": "https://example.org/source",
                        "media_type": "text",
                        "title": "示例资料",
                        "authorization_status": "authorized",
                    }
                ],
                "publish": True,
            },
            {"x-admin-token": "test-admin"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json_body(raw)["accepted_count"], 1)
        self.assertEqual(self.fake.calls[-1]["path"], "/v1/knowledge/ingest")


if __name__ == "__main__":
    unittest.main()
