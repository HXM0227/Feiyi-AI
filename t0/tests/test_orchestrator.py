from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from t0_orchestrator import Orchestrator, Settings, build_registry
from t0_orchestrator.contracts import MockModuleClient
from t0_orchestrator.errors import ModuleCallError, T0Error
from t0_orchestrator.models import (
    ContentGenerateRequest,
    FeedbackRequest,
    GuideQueryRequest,
    KnowledgeIngestRequest,
)


class FailingClient(MockModuleClient):
    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        raise ModuleCallError(self.module_id, "test failure")

class InvalidResponseClient(MockModuleClient):
    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        return {}


def service() -> Orchestrator:
    settings = Settings(mode="mock", contract_version="1.0.0")
    return Orchestrator(settings, build_registry(settings))


def query(**options: Any) -> GuideQueryRequest:
    return GuideQueryRequest.model_validate(
        {
            "session_id": "s-001",
            "target_language": "en",
            "input": {"type": "text", "text": "请介绍这项非遗"},
            "options": {"debug": True, **options},
        }
    )


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_guide_query_happy_path_and_idempotency(self) -> None:
        app = service()
        first = await app.guide_query(query(return_audio=True), idempotency_key="same")
        second = await app.guide_query(query(return_audio=True), idempotency_key="same")
        self.assertEqual(first.trace_id, second.trace_id)
        self.assertIn("source-grounded", first.answer)
        self.assertEqual(len(first.citations), 2)
        self.assertIsNotNone(first.audio)
        self.assertEqual(
            [step.module_id for step in first.pipeline],
            ["T6", "T3", "T2", "T5", "T4", "T6"],
        )

    async def test_idempotency_key_is_scoped_to_session(self) -> None:
        app = service()
        first = await app.guide_query(query(), idempotency_key="same")
        other_session = query().model_copy(update={"session_id": "s-002"})
        second = await app.guide_query(other_session, idempotency_key="same")
        self.assertNotEqual(first.trace_id, second.trace_id)

    async def test_t2_failure_is_degraded(self) -> None:
        app = service()
        app.registry.clients["T2"] = FailingClient("T2")
        response = await app.guide_query(query())
        self.assertTrue(any("T2" in warning for warning in response.warnings))
        step = next(
            item
            for item in response.pipeline
            if item.module_id == "T2" and item.action == "graph_context"
        )
        self.assertEqual(step.status, "degraded")

    async def test_t5_failure_uses_safe_policy(self) -> None:
        app = service()
        app.registry.clients["T5"] = FailingClient("T5")
        response = await app.guide_query(query())
        self.assertTrue(any("T5" in warning for warning in response.warnings))
        self.assertEqual(response.pipeline[3].status, "degraded")

    async def test_t3_failure_stops_ungrounded_generation(self) -> None:
        app = service()
        app.registry.clients["T3"] = FailingClient("T3")
        with self.assertRaises(ModuleCallError):
            await app.guide_query(query())

    async def test_content_generation(self) -> None:
        app = service()
        response = await app.generate_content(
            ContentGenerateRequest.model_validate(
                {
                    "topic": "传统技艺",
                    "target_language": "en",
                    "platform": "social",
                }
            )
        )
        self.assertTrue(response.review_required)
        self.assertEqual(len(response.citations), 2)

    async def test_invalid_t8_response_is_mapped_to_contract_error(self) -> None:
        app = service()
        app.registry.clients["T8"] = InvalidResponseClient("T8")
        with self.assertRaises(T0Error) as raised:
            await app.generate_content(
                ContentGenerateRequest.model_validate(
                    {
                        "topic": "传统技艺",
                        "target_language": "en",
                        "platform": "social",
                    }
                )
            )
        self.assertEqual(raised.exception.code, "INVALID_MODULE_RESPONSE")

    async def test_knowledge_ingest(self) -> None:
        app = service()
        response = await app.ingest_knowledge(
            KnowledgeIngestRequest.model_validate(
                {
                    "documents": [
                        {
                            "source_id": "SRC-1",
                            "source_uri": "https://example.org/source/1",
                            "media_type": "document",
                            "title": "示例资料",
                            "authorization_status": "authorized",
                            "entities": [
                                {
                                    "entity_id": "E-T0-1",
                                    "entity_type": "craft",
                                    "canonical_name": "示例技艺",
                                    "aliases": ["demo craft"],
                                }
                            ],
                        }
                    ]
                }
            )
        )
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.accepted_count, 1)

    async def test_invalid_t9_feedback_response_is_mapped_to_contract_error(self) -> None:
        app = service()
        app.registry.clients["T9"] = InvalidResponseClient("T9")
        with self.assertRaises(T0Error) as raised:
            await app.submit_feedback(
                FeedbackRequest.model_validate(
                    {
                        "trace_id": "trace-001",
                        "session_id": "s-001",
                        "rating": "up",
                    }
                )
            )
        self.assertEqual(raised.exception.code, "INVALID_MODULE_RESPONSE")


if __name__ == "__main__":
    unittest.main()
