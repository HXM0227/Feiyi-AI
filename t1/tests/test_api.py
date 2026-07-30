from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from t1.t1_service.api import create_app
    from t1.t1_service.config import Settings
except ImportError:  # pragma: no cover - dependency availability varies by environment
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI dependencies are not installed")
class ApiTests(unittest.TestCase):
    def _client(self, directory: str, **kwargs: object) -> TestClient:
        settings = Settings(db_path=str(Path(directory) / "t1.db"), **kwargs)
        return TestClient(create_app(settings))

    @staticmethod
    def _text_document(source_id: str = "SRC-1", text: str = "????????", **metadata: object) -> dict:
        return {
            "source_id": source_id,
            "source_uri": f"https://example.org/{source_id}",
            "media_type": "text",
            "title": "????",
            "authorization_status": "authorized",
            "metadata": {"text": text, "language": "zh-CN", **metadata},
        }

    def test_health_ready_and_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            health = client.get("/healthz")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")
            ready = client.get("/readyz")
            self.assertEqual(ready.status_code, 200)
            self.assertTrue(ready.json()["ready"])
            capabilities = client.get("/v1/capabilities")
            self.assertEqual(capabilities.status_code, 200)
            self.assertIn("text", capabilities.json()["media_types"])
            self.assertIn("image", capabilities.json()["pre_extracted_media_types"])

    def test_readyz_reports_database_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            app = client.app
            def fail_ready() -> None:
                raise RuntimeError("database unavailable")
            app.state.ledger.check_ready = fail_ready
            response = client.get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json()["ready"])
            self.assertEqual(response.json()["code"], "DATABASE_NOT_READY")

    def test_health_and_normalize_with_correlation_headers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            response = client.post(
                "/v1/documents/normalize",
                headers={"X-Trace-ID": "trace-1", "X-Request-ID": "request-1"},
                json={"documents": [self._text_document()], "publish": False},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["records"][0]["chunks"][0]["chunk_id"], "SRC-1-0001")
            self.assertEqual(response.headers["X-Trace-ID"], "trace-1")
            self.assertEqual(response.headers["X-Request-ID"], "request-1")

    def test_correlation_headers_are_generated_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            response = client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers.get("X-Trace-ID"))
            self.assertTrue(response.headers.get("X-Request-ID"))

    def test_normalize_is_deterministic_for_same_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory, max_chunk_chars=20, chunk_overlap=3)
            document = self._text_document(text="????????????" * 8)
            first = client.post("/v1/documents/normalize", json={"documents": [document]})
            second = client.post("/v1/documents/normalize", json={"documents": [document]})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["records"], second.json()["records"])
            self.assertGreater(len(first.json()["records"][0]["chunks"]), 1)
            self.assertTrue(all(chunk["text"] for chunk in first.json()["records"][0]["chunks"]))

    def test_missing_text_is_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            document = self._text_document()
            document["metadata"] = {}
            response = client.post("/v1/documents/normalize", json={"documents": [document]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["records"], [])
            self.assertEqual(response.json()["rejected"][0]["code"], "MISSING_TEXT")

    def test_mixed_batch_returns_success_and_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            missing = self._text_document("SRC-MISSING")
            missing["metadata"] = {}
            response = client.post(
                "/v1/documents/normalize",
                json={"documents": [self._text_document("SRC-OK"), missing]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r["source_id"] for r in response.json()["records"]], ["SRC-OK"])
            self.assertEqual(response.json()["rejected"][0]["source_id"], "SRC-MISSING")

    def test_unknown_fields_and_unsupported_media_are_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            response = client.post(
                "/v1/documents/normalize",
                json={
                    "documents": [{
                        "source_id": "SRC-IMAGE",
                        "source_uri": "https://example.org/image",
                        "media_type": "image",
                        "title": "????",
                        "authorization_status": "public",
                        "metadata": {},
                        "future_field": "ignored",
                    }],
                    "future_request_field": True,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["records"], [])
            self.assertEqual(response.json()["rejected"][0]["code"], "UNSUPPORTED_MEDIA_FOR_MVP")

    def test_pre_extracted_media_text_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            document = self._text_document("SRC-AUDIO")
            document["media_type"] = "audio"
            response = client.post("/v1/documents/normalize", json={"documents": [document]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["records"][0]["media_type"], "audio")

    def test_publish_does_not_upgrade_restricted_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            document = self._text_document("SRC-RESTRICTED")
            document["authorization_status"] = "restricted"
            response = client.post(
                "/v1/documents/normalize",
                json={"documents": [document], "publish": True},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["records"][0]["authorization_status"], "restricted")
            self.assertTrue(any("publish=true" in warning for warning in response.json()["warnings"]))

    def test_sources_returns_persisted_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            client.post("/v1/documents/normalize", json={"documents": [self._text_document("SRC-LEDGER")]})
            response = client.get("/v1/sources")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["sources"][0]["source_id"], "SRC-LEDGER")
            self.assertEqual(len(response.json()["sources"][0]["content_hash"]), 64)

    def test_invalid_request_returns_stable_error_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory)
            response = client.post("/v1/documents/normalize", json={"documents": []})
            self.assertEqual(response.status_code, 422)
            payload = response.json()
            self.assertEqual(payload["code"], "VALIDATION_ERROR")
            self.assertIn("trace_id", payload)

    def test_configured_bearer_token_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = self._client(directory, api_token="secret")
            response = client.get("/v1/sources")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["code"], "UNAUTHORIZED")
            self.assertEqual(response.json()["message"], "\u672a\u63d0\u4f9b\u6709\u6548\u7684\u8bbf\u95ee\u4ee4\u724c")
            response = client.get("/v1/sources", headers={"Authorization": "Bearer secret"})
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
