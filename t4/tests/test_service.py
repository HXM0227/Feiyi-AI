from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from t4_multilingual.config import Settings
from t4_multilingual.schemas import GenerationRequest
from t4_multilingual.service import GenerationService


ROOT = Path(__file__).resolve().parents[1]


def sample_request(target: str = "en") -> GenerationRequest:
    data = json.loads((ROOT / "data" / "sample_context.json").read_text(encoding="utf-8"))
    data["target_language"] = target
    return GenerationRequest.model_validate(data)


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, directory: Path, mode: str = "mock") -> Settings:
        return Settings(
            mode=mode,
            terminology_path=ROOT / "data" / "terminology_zh_en.json",
            audit_dir=directory / "audit",
        )

    async def test_chinese_to_english_keeps_term_and_citations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            response = await GenerationService(self.settings(Path(temp))).generate(sample_request())
        self.assertIn("Paper Cutting (剪纸)", response.answer)
        self.assertEqual(response.used_citation_ids, ["CIT-001", "CIT-002"])
        self.assertTrue(response.terminology_check.passed)
        self.assertEqual(response.generator_mode, "mock")

    async def test_english_to_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            response = await GenerationService(self.settings(Path(temp))).generate(sample_request("zh-CN"))
        self.assertIn("剪纸", response.answer)
        self.assertEqual(response.target_language, "zh-CN")

    async def test_qwen_failure_falls_back_to_mock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            service = GenerationService(replace(self.settings(Path(temp), "qwen"), qwen_api_key="not-a-real-key"))

            async def fail(*_: object) -> str:
                from t4_multilingual.service import GenerationError
                raise GenerationError("simulated")

            service.qwen.generate = fail  # type: ignore[method-assign]
            response = await service.generate(sample_request())
        self.assertTrue(response.fallback_used)
        self.assertEqual(response.generator_mode, "fallback_mock")

    async def test_audit_record_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            await GenerationService(self.settings(directory)).generate(sample_request())
            audit = directory / "audit" / "generation_audit.jsonl"
            self.assertTrue(audit.exists())
            self.assertIn('"used_citation_ids"', audit.read_text(encoding="utf-8"))

    def test_unsupported_language_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sample_request("ja")


if __name__ == "__main__":
    unittest.main()
