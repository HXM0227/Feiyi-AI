from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from t6_input_media.api import create_app
from t6_input_media.config import Settings
from t6_input_media.dashscope_client import AsrError, TtsError


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(Settings()))

    def test_health_and_ready(self) -> None:
        for path in ("/healthz", "/readyz"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["mode"], "mock")

    def test_normalize_matches_t0_payload_shape(self) -> None:
        response = self.client.post(
            "/v1/input/normalize",
            headers={"X-Trace-ID": "trace-1", "X-Request-ID": "request-1"},
            json={
                "input": {"type": "text", "text": "What is paper cutting?"},
                "source_language": "auto",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["query"], "What is paper cutting?")
        self.assertEqual(response.json()["detected_language"], "en")

    def test_synthesis_response_has_only_t0_audio_asset_fields(self) -> None:
        response = self.client.post(
            "/v1/audio/synthesize",
            json={"text": "A source-grounded guide.", "language": "en", "voice": "narrator"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"url", "mime_type", "voice"})
        self.assertEqual(response.json()["voice"], "narrator")

    def test_extra_contract_fields_are_rejected(self) -> None:
        response = self.client.post(
            "/v1/input/normalize",
            json={
                "input": {"type": "text", "text": "剪纸", "unexpected": True},
                "source_language": "auto",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "VALIDATION_ERROR")

    def test_unsupported_language_is_unprocessable(self) -> None:
        response = self.client.post(
            "/v1/audio/synthesize",
            json={"text": "Bonjour", "language": "fr"},
        )
        self.assertEqual(response.status_code, 422)

    def test_asr_provider_failure_maps_to_bad_gateway(self) -> None:
        client = TestClient(
            create_app(
                Settings(mode="dashscope", dashscope_api_key="test-key-not-real")
            )
        )
        with patch(
            "t6_input_media.service.DashScopeAsrClient.transcribe",
            side_effect=AsrError("provider unavailable"),
        ):
            response = client.post(
                "/v1/input/normalize",
                json={
                    "input": {
                        "type": "audio",
                        "media_url": "https://audio.example.org/demo.mp3",
                    },
                    "source_language": "auto",
                },
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "provider unavailable")

    def test_tts_provider_failure_maps_to_bad_gateway(self) -> None:
        client = TestClient(
            create_app(
                Settings(mode="dashscope", dashscope_api_key="test-key-not-real")
            )
        )
        with patch(
            "t6_input_media.service.DashScopeTtsClient.synthesize",
            side_effect=TtsError("provider unavailable"),
        ):
            response = client.post(
                "/v1/audio/synthesize",
                json={"text": "A guide", "language": "en"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "provider unavailable")


if __name__ == "__main__":
    unittest.main()
