from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from t0_orchestrator import Orchestrator, Settings, build_registry
from t0_orchestrator.models import GuideQueryRequest


async def main() -> None:
    settings = Settings(mode="mock", contract_version="1.0.0")
    service = Orchestrator(settings, build_registry(settings))
    request = GuideQueryRequest.model_validate(
        {
            "session_id": "demo-session-001",
            "target_language": "en",
            "input": {"type": "text", "text": "这项非遗工艺为什么重要？"},
            "audience": {
                "region": "Europe",
                "age_band": "adult",
                "knowledge_level": "beginner",
                "style": "story",
            },
            "options": {"return_audio": True, "debug": True},
        }
    )
    response = await service.guide_query(request, idempotency_key="demo-001")
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
