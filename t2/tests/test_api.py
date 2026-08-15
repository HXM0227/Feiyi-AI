from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from t2_service.api import create_app
from t2_service.config import Settings


def sample_payload(status: str = "authorized") -> dict[str, Any]:
    return {
        "records": [
            {
                "source_id": "SRC-T2-001",
                "title": "剪纸知识样例",
                "source_uri": "https://example.org/t2/001",
                "media_type": "text",
                "authorization_status": status,
                "metadata": {"language": "zh-CN", "version": "0.1"},
                "chunks": [
                    {
                        "chunk_id": "SRC-T2-001-0001",
                        "text": "蔚县剪纸是中国剪纸的地域性实践。",
                        "sequence": 1,
                        "section": "关系",
                        "language": "zh-CN",
                    }
                ],
                "entities": [
                    {
                        "entity_id": "E-PAPERCUT",
                        "entity_type": "craft",
                        "canonical_name": "剪纸",
                        "aliases": ["中国剪纸", "paper cutting"],
                        "language": "zh-CN",
                    },
                    {
                        "entity_id": "E-YUXIAN",
                        "entity_type": "place",
                        "canonical_name": "蔚县剪纸",
                        "aliases": ["蔚县窗花"],
                        "language": "zh-CN",
                    },
                ],
                "relations": [
                    {
                        "relation_id": "R-T2-001",
                        "subject_id": "E-YUXIAN",
                        "predicate": "example_of",
                        "object_id": "E-PAPERCUT",
                        "chunk_id": "SRC-T2-001-0001",
                    }
                ],
            }
        ]
    }


async def asgi_request(
    app,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
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

    raw_headers = {"content-type": "application/json", **(headers or {})}
    query = b""
    if "?" in path:
        path, query_string = path.split("?", 1)
        query = query_string.encode("ascii")
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode("utf-8"),
        "query_string": query,
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in raw_headers.items()],
        "client": ("127.0.0.1", 12345), "server": ("testserver", 80), "root_path": "",
    }
    await app(scope, receive, send)
    start = next(item for item in messages if item["type"] == "http.response.start")
    response_body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
    response_headers = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return start["status"], json.loads(response_body), response_headers


class T2ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.app = create_app(Settings(db_path=":memory:"))

    async def asyncTearDown(self) -> None:
        self.app.state.store.close()

    async def test_health_ready_capabilities_and_trace(self) -> None:
        status, body, headers = await asgi_request(
            self.app, "GET", "/healthz", headers={"X-Trace-ID": "trace-health", "X-Request-ID": "request-health"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["module"], "T2")
        self.assertEqual(headers["x-trace-id"], "trace-health")
        self.assertEqual(headers["x-request-id"], "request-health")
        status, body, _ = await asgi_request(self.app, "GET", "/readyz")
        self.assertEqual(status, 200)
        self.assertTrue(body["ready"])
        status, body, _ = await asgi_request(self.app, "GET", "/v1/capabilities")
        self.assertEqual(status, 200)
        self.assertIn("graph", " ".join(body["routes"]))

    async def test_upsert_query_alias_type_relation_and_idempotency(self) -> None:
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/upsert", sample_payload())
        self.assertEqual(status, 200)
        self.assertEqual(body["accepted_count"], 1)
        self.assertEqual(body["entity_count"], 2)
        self.assertEqual(body["relation_count"], 1)
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/upsert", sample_payload())
        self.assertEqual(status, 200)
        self.assertEqual(body["entity_count"], 2)
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", {"name": "剪纸"})
        self.assertEqual(status, 200)
        self.assertEqual(body["entities"][0]["entity_id"], "E-PAPERCUT")
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", {"alias": "蔚县窗花", "entity_type": "place"})
        self.assertEqual(status, 200)
        self.assertEqual(body["entities"][0]["canonical_name"], "蔚县剪纸")
        self.assertEqual(body["relations"][0]["source_id"], "SRC-T2-001")
        self.assertEqual(body["relations"][0]["chunk_id"], "SRC-T2-001-0001")
        status, body, _ = await asgi_request(self.app, "GET", "/v1/graph/entities/E-YUXIAN")
        self.assertEqual(status, 200)
        self.assertEqual(body["entity"]["canonical_name"], "蔚县剪纸")
        self.assertEqual(len(body["relations"]), 1)
        status, body, _ = await asgi_request(self.app, "GET", "/v1/graph/relations?subject_id=E-YUXIAN")
        self.assertEqual(status, 200)
        self.assertEqual(body["relations"][0]["relation_id"], "R-T2-001")

    async def test_relation_source_authorization_change_is_filtered(self) -> None:
        payload = sample_payload("authorized")
        await asgi_request(self.app, "POST", "/v1/graph/upsert", payload)
        changed = sample_payload("restricted")
        await asgi_request(self.app, "POST", "/v1/graph/upsert", changed)
        status, body, _ = await asgi_request(
            self.app, "POST", "/v1/graph/query", {"entity_id": "E-YUXIAN"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["entities"], [])
        self.assertEqual(body["relations"], [])

    async def test_authorization_filter_cannot_be_bypassed(self) -> None:
        restricted = sample_payload("restricted")
        restricted["records"][0]["source_id"] = "SRC-T2-RESTRICTED"
        restricted["records"][0]["chunks"][0]["chunk_id"] = "SRC-T2-RESTRICTED-0001"
        restricted["records"][0]["relations"][0]["chunk_id"] = "SRC-T2-RESTRICTED-0001"
        await asgi_request(self.app, "POST", "/v1/graph/upsert", restricted)
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", {"name": "剪纸", "filters": {"authorization_status": ["restricted"]}})
        self.assertEqual(status, 200)
        self.assertEqual(body["entities"], [])
        self.assertEqual(body["relations"], [])
        for query in (
            {"entity_id": "E-YUXIAN"},
            {"alias": "蔚县窗花"},
            {"predicate": "example_of"},
        ):
            status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", query)
            self.assertEqual(status, 200)
            self.assertEqual(body["entities"], [])
            self.assertEqual(body["relations"], [])
        status, body, _ = await asgi_request(self.app, "GET", "/v1/graph/entities/E-YUXIAN")
        self.assertEqual(status, 200)
        self.assertIsNone(body["entity"])
        self.assertEqual(body["relations"], [])
        status, body, _ = await asgi_request(self.app, "GET", "/v1/graph/relations?entity_id=E-YUXIAN")
        self.assertEqual(status, 200)
        self.assertEqual(body["relations"], [])
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", {"name": "不存在"})
        self.assertEqual(status, 200)
        self.assertEqual(body["entities"], [])

    async def test_invalid_reference_is_rejected(self) -> None:
        payload = sample_payload()
        payload["records"][0]["relations"][0]["object_id"] = "MISSING"
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/upsert", payload)
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "INVALID_GRAPH_DATA")

    async def test_empty_query_is_rejected(self) -> None:
        status, body, _ = await asgi_request(self.app, "POST", "/v1/graph/query", {})
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
