from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from t8_content_generation.config import Settings
from t8_content_generation.schemas import ContentGenerationRequest
from t8_content_generation.service import (
    ContentGenerationError,
    ContentGenerationService,
)


ROOT = Path(__file__).resolve().parents[1]


def request_data(
    *,
    platform: str = "social",
    language: str = "en",
    max_length: int = 500,
) -> dict:
    data = json.loads(
        (ROOT / "examples" / "requests" / "generate-paper-cutting-en.json").read_text(
            encoding="utf-8"
        )
    )
    data["platform"] = platform
    data["target_language"] = language
    data["max_length"] = max_length
    return data


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, directory: Path, mode: str = "mock") -> Settings:
        return Settings(
            mode=mode,
            template_path=ROOT / "data" / "platform_templates.json",
            audit_dir=directory / "audit",
        )

    async def test_all_platforms_and_languages_generate_grounded_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            service = ContentGenerationService(self.settings(Path(temp)))
            for platform in ("short_video", "poster", "social", "event_intro"):
                for language in ("zh-CN", "en"):
                    with self.subTest(platform=platform, language=language):
                        request = ContentGenerationRequest.model_validate(
                            request_data(platform=platform, language=language)
                        )
                        response = await service.generate(request)
                        self.assertTrue(response.content)
                        self.assertEqual(response.used_citation_ids, ["CIT-001"])
                        self.assertTrue(response.review_required)
                        self.assertLessEqual(response.length, request.max_length)
                        self.assertEqual(response.generator_mode, "mock")

    async def test_unicode_length_limit_preserves_complete_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = ContentGenerationRequest.model_validate(
                request_data(language="zh-CN", max_length=50)
            )
            response = await ContentGenerationService(
                self.settings(Path(temp))
            ).generate(request)
        self.assertLessEqual(len(response.content), 50)
        self.assertTrue(response.content.endswith("[CIT-001]"))
        self.assertNotIn("[CIT-00…", response.content)

    async def test_cross_language_mock_does_not_echo_foreign_excerpt(self) -> None:
        data = request_data(language="en")
        data["context"][0]["excerpt"] = "剪纸以纸张为材料，通过剪刀或刻刀形成纹样。"
        with tempfile.TemporaryDirectory() as temp:
            response = await ContentGenerationService(
                self.settings(Path(temp))
            ).generate(ContentGenerationRequest.model_validate(data))
        self.assertNotIn("剪纸以纸张为材料", response.content)
        self.assertIn("Human translation and review", response.content)
        self.assertTrue(response.warnings)
        self.assertEqual(response.used_citation_ids, ["CIT-001"])

    async def test_duplicate_citations_are_deduplicated_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            service = ContentGenerationService(self.settings(Path(temp)))
            request = ContentGenerationRequest.model_validate(request_data())
            used = service._validate_output(
                "Draft [CIT-001] more detail [CIT-001]", request
            )
        self.assertEqual(used, ["CIT-001"])

    async def test_unknown_model_citation_causes_qwen_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(
                self.settings(Path(temp), "qwen"), qwen_api_key="test-key"
            )
            service = ContentGenerationService(settings)

            async def invalid(_: ContentGenerationRequest) -> str:
                return "Invented claim [CIT-NOT-ALLOWED]"

            service.qwen.generate = invalid  # type: ignore[method-assign]
            response = await service.generate(
                ContentGenerationRequest.model_validate(request_data())
            )
        self.assertEqual(response.generator_mode, "fallback_mock")
        self.assertTrue(response.fallback_used)
        self.assertEqual(response.used_citation_ids, ["CIT-001"])
        self.assertTrue(response.warnings)

    async def test_qwen_over_length_causes_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(
                self.settings(Path(temp), "qwen"), qwen_api_key="test-key"
            )
            service = ContentGenerationService(settings)

            async def too_long(_: ContentGenerationRequest) -> str:
                return "x" * 80 + "[CIT-001]"

            service.qwen.generate = too_long  # type: ignore[method-assign]
            response = await service.generate(
                ContentGenerationRequest.model_validate(request_data(max_length=50))
            )
        self.assertTrue(response.fallback_used)
        self.assertLessEqual(response.length, 50)

    async def test_qwen_wrong_language_causes_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(
                self.settings(Path(temp), "qwen"), qwen_api_key="test-key"
            )
            service = ContentGenerationService(settings)

            async def wrong_language(_: ContentGenerationRequest) -> str:
                return "这是一段中文内容。[CIT-001]"

            service.qwen.generate = wrong_language  # type: ignore[method-assign]
            response = await service.generate(
                ContentGenerationRequest.model_validate(request_data(language="en"))
            )
        self.assertTrue(response.fallback_used)
        self.assertIn("language mismatch", response.warnings[0])

    async def test_qwen_failure_causes_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = replace(
                self.settings(Path(temp), "qwen"), qwen_api_key="test-key"
            )
            service = ContentGenerationService(settings)

            async def fail(_: ContentGenerationRequest) -> str:
                raise ContentGenerationError("simulated failure")

            service.qwen.generate = fail  # type: ignore[method-assign]
            response = await service.generate(
                ContentGenerationRequest.model_validate(request_data())
            )
        self.assertEqual(response.generator_mode, "fallback_mock")
        self.assertTrue(response.review_required)

    async def test_audit_record_contains_no_context_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            request = ContentGenerationRequest.model_validate(request_data())
            await ContentGenerationService(self.settings(directory)).generate(request)
            path = directory / "audit" / "content_generation_audit.jsonl"
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["source_ids"], ["SRC-PAPER-CUTTING-001"])
        self.assertNotIn("context", record)
        self.assertTrue(record["review_required"])

    def test_unsupported_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ContentGenerationRequest.model_validate(request_data(language="ja"))

    def test_human_review_cannot_be_disabled(self) -> None:
        data = request_data()
        data["requirements"]["human_review"] = False
        with self.assertRaises(ValueError):
            ContentGenerationRequest.model_validate(data)


if __name__ == "__main__":
    unittest.main()
