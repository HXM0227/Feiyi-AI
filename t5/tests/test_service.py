from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from t5_cultural_adaptation.config import DEFAULT_POLICY_PATH
from t5_cultural_adaptation.schemas import AdaptationRequest
from t5_cultural_adaptation.service import AdaptationService, PolicyLoadError


def sample_request(**audience_updates: str) -> AdaptationRequest:
    audience = {
        "region": "global",
        "age_band": "adult",
        "knowledge_level": "general",
        "style": "educational",
        **audience_updates,
    }
    return AdaptationRequest.model_validate(
        {
            "query": "请介绍剪纸",
            "target_language": "en",
            "audience": audience,
            "graph_context": {},
            "retrieval_context": [
                {
                    "citation_id": "CIT-001",
                    "source_id": "SRC-001",
                    "title": "剪纸资料",
                    "excerpt": "剪纸是一种传统工艺。",
                    "score": 0.9,
                }
            ],
        }
    )


class AdaptationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AdaptationService.from_path(DEFAULT_POLICY_PATH)

    def test_same_input_is_deterministic(self) -> None:
        request = sample_request()
        first = self.service.adapt(request)
        second = self.service.adapt(request)
        self.assertEqual(first, second)
        self.assertEqual(first.policy_version, "t5-cultural-policy-1.0.0")

    def test_child_beginner_story_rules_are_selected(self) -> None:
        response = self.service.adapt(
            sample_request(
                region="Japan",
                age_band="child",
                knowledge_level="beginner",
                style="story",
            )
        )
        joined = "\n".join(response.instructions)
        self.assertIn("儿童", joined)
        self.assertIn("一句话定义", joined)
        self.assertIn("不得虚构人物", joined)
        self.assertIn("不据此推断民族性格", joined)
        self.assertNotIn("Japan", joined)

    def test_language_specific_blocked_terms_are_returned_and_instructed(self) -> None:
        response = self.service.adapt(sample_request())
        self.assertIn("uncivilized people", response.blocked_terms)
        self.assertIn("uncivilized people", response.instructions[-1])

        request = sample_request().model_copy(update={"target_language": "zh-CN"})
        chinese = self.service.adapt(request)
        self.assertIn("未开化民族", chinese.blocked_terms)
        self.assertNotIn("uncivilized people", chinese.blocked_terms)

    def test_output_does_not_copy_or_create_request_citations(self) -> None:
        response = self.service.adapt(sample_request())
        joined = "\n".join(response.instructions)
        self.assertNotIn("CIT-001", joined)
        self.assertNotIn("剪纸是一种传统工艺", joined)

    def test_missing_policy_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PolicyLoadError):
                AdaptationService.from_path(Path(temp) / "missing.json")

    def test_unknown_policy_key_fails_fast(self) -> None:
        payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
        payload["style"]["marketing"] = "不应被静默接受的规则。"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "policies.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(PolicyLoadError):
                AdaptationService.from_path(path)

    def test_duplicate_blocked_term_fails_fast(self) -> None:
        payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
        payload["blocked_terms"]["en"].append("MYSTERIOUS EAST")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "policies.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(PolicyLoadError):
                AdaptationService.from_path(path)


if __name__ == "__main__":
    unittest.main()
