from __future__ import annotations

import unittest

from t6_input_media.config import Settings
from t6_input_media.schemas import NormalizeRequest, SynthesizeRequest
from t6_input_media.service import InputMediaService, InputNormalizationError


class InputMediaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InputMediaService(Settings())

    def test_auto_detects_chinese_text(self) -> None:
        result = self.service.normalize(
            NormalizeRequest(input={"type": "text", "text": "请介绍剪纸的工艺"})
        )
        self.assertEqual(result.query, "请介绍剪纸的工艺")
        self.assertEqual(result.detected_language, "zh-CN")
        self.assertGreater(result.confidence, 0.75)

    def test_explicit_english_is_respected(self) -> None:
        result = self.service.normalize(
            NormalizeRequest(
                input={"type": "text", "text": "Tell me about paper cutting."},
                source_language="en-US",
            )
        )
        self.assertEqual(result.detected_language, "en")
        self.assertEqual(result.confidence, 1.0)

    def test_exhibit_id_generates_stable_query(self) -> None:
        result = self.service.normalize(
            NormalizeRequest(
                input={"type": "exhibit_id", "exhibit_id": "EX-001"},
                source_language="en",
            )
        )
        self.assertEqual(result.query, "Please introduce exhibit EX-001.")
        self.assertEqual(result.detected_language, "en")

    def test_media_with_auto_language_is_explicitly_unknown(self) -> None:
        result = self.service.normalize(
            NormalizeRequest(
                input={"type": "audio", "media_url": "https://example.org/demo.mp3"}
            )
        )
        self.assertEqual(result.detected_language, "unknown")
        self.assertEqual(result.confidence, 0.0)

    def test_unsupported_language_is_rejected(self) -> None:
        request = NormalizeRequest(
            input={"type": "text", "text": "bonjour"}, source_language="fr"
        )
        with self.assertRaises(InputNormalizationError):
            self.service.normalize(request)

    def test_synthesis_is_deterministic_mock_asset(self) -> None:
        request = SynthesizeRequest(text="测试讲解", language="zh")
        first = self.service.synthesize(request)
        second = self.service.synthesize(request)
        self.assertEqual(first, second)
        self.assertTrue(first.url.startswith("mock://audio/"))
        self.assertEqual(first.mime_type, "audio/mpeg")
        self.assertEqual(first.voice, "default")


if __name__ == "__main__":
    unittest.main()
