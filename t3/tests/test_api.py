from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from t3.t3_service.api import create_app
from t3.t3_service.config import Settings


class T3ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(Settings(db_path=str(Path(self.temp_dir.name) / "t3.db")))

    def tearDown(self) -> None:
        self.app.state.index.close()
        self.temp_dir.cleanup()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    def test_health_ready_capabilities_and_header_passthrough(self) -> None:
        async def scenario() -> None:
            health = await self.request("GET", "/healthz", headers={"X-Trace-ID": "trace-1", "X-Request-ID": "request-1"})
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")
            self.assertEqual(health.headers["X-Trace-ID"], "trace-1")
            self.assertEqual(health.headers["X-Request-ID"], "request-1")
            ready = await self.request("GET", "/readyz")
            self.assertEqual(ready.status_code, 200)
            capabilities = await self.request("GET", "/v1/capabilities")
            self.assertEqual(capabilities.json()["module"], "T3")
        asyncio.run(scenario())

    def test_empty_upsert_and_retrieve(self) -> None:
        async def scenario() -> None:
            response = await self.request("POST", "/v1/index/upsert", json={"records": []})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["accepted_count"], 0)
            result = await self.request("POST", "/v1/retrieve", json={"query": "没有命中", "top_k": 5})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {"chunks": []})
        asyncio.run(scenario())

    def test_upsert_retrieve_citation_and_filtering(self) -> None:
        async def scenario() -> None:
            payload = {
                "records": [
                    {
                        "source_id": "SRC-AUTH",
                        "title": "剪纸授权资料",
                        "source_uri": "https://example.org/paper-cutting",
                        "media_type": "text",
                        "authorization_status": "authorized",
                        "metadata": {"language": "zh-CN", "version": "0.1"},
                        "chunks": [{"chunk_id": "SRC-AUTH-0001", "text": "剪纸的历史与工艺流程。", "sequence": 1, "section": "历史与工艺", "language": "zh-CN"}],
                    },
                    {
                        "source_id": "SRC-UNKNOWN",
                        "title": "未知授权资料",
                        "source_uri": "https://example.org/unknown",
                        "media_type": "text",
                        "authorization_status": "unknown",
                        "metadata": {"language": "zh-CN"},
                        "chunks": [{"chunk_id": "SRC-UNKNOWN-0001", "text": "剪纸的历史与工艺流程。", "sequence": 1, "section": "历史与工艺", "language": "zh-CN"}],
                    },
                ],
                "publish": False,
            }
            upsert = await self.request("POST", "/v1/index/upsert", json=payload, headers={"X-Trace-ID": "trace-upsert"})
            self.assertEqual(upsert.status_code, 200)
            self.assertEqual(upsert.json()["accepted_count"], 2)
            self.assertEqual(upsert.json()["indexed_count"], 2)
            self.assertTrue(upsert.json()["warnings"])
            result = await self.request("POST", "/v1/retrieve", json={"query": "剪纸历史工艺", "language": "zh-CN", "top_k": 5})
            self.assertEqual(result.status_code, 200)
            chunks = result.json()["chunks"]
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0]["source_id"], "SRC-AUTH")
            self.assertEqual(set(chunks[0]), {"citation_id", "source_id", "title", "section", "uri", "excerpt", "score"})
            self.assertGreater(chunks[0]["score"], 0)
        asyncio.run(scenario())

    def test_validation_error_is_unified(self) -> None:
        async def scenario() -> None:
            response = await self.request("POST", "/v1/retrieve", json={"query": "", "top_k": 0}, headers={"X-Trace-ID": "trace-invalid"})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
            self.assertEqual(response.json()["trace_id"], "trace-invalid")
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
