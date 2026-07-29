"""Generate a bilingual acceptance report. In mock mode it remains fully reproducible."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from t4_multilingual.config import Settings
from t4_multilingual.schemas import GenerationRequest
from t4_multilingual.service import GenerationService


async def main() -> None:
    root = ROOT
    data = json.loads((root / "data" / "sample_context.json").read_text(encoding="utf-8"))
    settings = replace(
        Settings.from_env(),
        terminology_path=root / "data" / "terminology_zh_en.json",
        audit_dir=root / "runtime" / "audit",
    )
    service = GenerationService(settings)
    forward = await service.generate(GenerationRequest.model_validate(data))
    reverse_data = {**data, "query": forward.answer, "detected_language": "en", "target_language": "zh-CN"}
    reverse = await service.generate(GenerationRequest.model_validate(reverse_data))
    report = {
        "original_text": data["query"],
        "target_text": forward.answer,
        "back_translation": reverse.answer,
        "terminology_check": forward.terminology_check.model_dump(),
        "citation_check": {"passed": bool(forward.used_citation_ids), "used_citation_ids": forward.used_citation_ids},
        "human_review_conclusion": "待人工复核：核对文化寓意是否符合具体纹样和地区语境。",
    }
    output = root / "examples" / "back_translation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.name)


if __name__ == "__main__":
    asyncio.run(main())
