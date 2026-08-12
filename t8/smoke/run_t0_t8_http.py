from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


T8_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = T8_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "t0"))

from t0_orchestrator import Orchestrator, Settings, build_registry  # noqa: E402
from t0_orchestrator.contracts import HttpModuleClient  # noqa: E402
from t0_orchestrator.models import ContentGenerateRequest  # noqa: E402


async def main() -> None:
    base_url = os.getenv("T8_BASE_URL", "http://127.0.0.1:8108").rstrip("/")
    settings = Settings(mode="mock", contract_version="1.0.0")
    orchestrator = Orchestrator(settings, build_registry(settings))
    orchestrator.registry.clients["T8"] = HttpModuleClient(
        module_id="T8",
        base_url=base_url,
        retry_count=0,
    )
    response = await orchestrator.generate_content(
        ContentGenerateRequest.model_validate(
            {
                "request_id": "t8-http-smoke",
                "topic": "传统技艺",
                "target_language": "en",
                "platform": "social",
                "max_length": 180,
            }
        )
    )
    if not response.content.strip():
        raise RuntimeError("T0 did not receive T8 content")
    if not response.review_required:
        raise RuntimeError("T8 content unexpectedly bypassed human review")
    if len(response.content) > 180:
        raise RuntimeError("T8 content exceeded max_length")
    print(
        json.dumps(
            {
                "status": "ok",
                "t8_base_url": base_url,
                "content_length": len(response.content),
                "citation_count_returned_by_t0": len(response.citations),
                "review_required": response.review_required,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
