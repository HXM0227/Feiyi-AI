from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


T5_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = T5_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "t0"))

from t0_orchestrator import Orchestrator, Settings, build_registry  # noqa: E402
from t0_orchestrator.contracts import HttpModuleClient, MockModuleClient  # noqa: E402
from t0_orchestrator.models import GuideQueryRequest  # noqa: E402


class CapturingT4Client(MockModuleClient):
    def __init__(self) -> None:
        super().__init__("T4")
        self.last_payload: dict[str, Any] | None = None

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        trace_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        self.last_payload = payload
        return await super().call(
            path,
            payload,
            trace_id=trace_id,
            request_id=request_id,
        )


async def main() -> None:
    base_url = os.getenv("T5_BASE_URL", "http://127.0.0.1:8105").rstrip("/")
    settings = Settings(mode="mock", contract_version="1.0.0")
    orchestrator = Orchestrator(settings, build_registry(settings))
    orchestrator.registry.clients["T5"] = HttpModuleClient(
        module_id="T5",
        base_url=base_url,
        retry_count=0,
    )
    capturing_t4 = CapturingT4Client()
    orchestrator.registry.clients["T4"] = capturing_t4

    request = GuideQueryRequest.model_validate(
        {
            "session_id": "t5-http-smoke",
            "target_language": "en",
            "input": {"type": "text", "text": "请介绍这项非遗"},
            "audience": {
                "region": "global",
                "age_band": "adult",
                "knowledge_level": "beginner",
                "style": "educational",
            },
            "options": {"debug": True},
        }
    )
    response = await orchestrator.guide_query(request)
    adaptation = (capturing_t4.last_payload or {}).get("adaptation", {})

    if adaptation.get("policy_version") != "t5-cultural-policy-1.0.0":
        raise RuntimeError("T4 未收到真实 T5 的版本化策略")
    if any("T5" in warning for warning in response.warnings):
        raise RuntimeError("T0 将真实 T5 调用标记为降级")
    t5_step = next(
        (step for step in response.pipeline if step.module_id == "T5"),
        None,
    )
    if t5_step is None or t5_step.status != "ok":
        raise RuntimeError("T0 流水线未记录成功的 T5 HTTP 调用")

    print(
        json.dumps(
            {
                "status": "ok",
                "t5_base_url": base_url,
                "policy_version": adaptation["policy_version"],
                "instruction_count": len(adaptation.get("instructions", [])),
                "pipeline_status": t5_step.status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
