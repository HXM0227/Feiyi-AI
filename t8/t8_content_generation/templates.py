from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import ContentGenerationRequest


class PlatformTemplates:
    def __init__(self, path: Path) -> None:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        self.version = str(payload["version"])
        self.platforms: dict[str, dict[str, dict[str, str]]] = payload["platforms"]

    def render(self, request: ContentGenerationRequest) -> str:
        language = request.target_language
        template = self.platforms[request.platform][language]
        audience = request.audience
        values = {
            "topic": request.topic.strip(),
            "excerpt": request.context[0].excerpt.strip(),
            "citation": f"[{request.context[0].citation_id}]",
            "audience_hint": self._audience_hint(language, audience.knowledge_level),
        }
        return template["body"].format(**values)

    @staticmethod
    def _audience_hint(language: str, knowledge_level: str) -> str:
        if language == "en":
            return {
                "beginner": "A clear starting point",
                "general": "A source-grounded perspective",
                "advanced": "A closer source-based view",
                "expert": "A concise source-based reference",
            }[knowledge_level]
        return {
            "beginner": "从一个清晰的要点开始",
            "general": "从有据可查的角度认识",
            "advanced": "进一步结合资料理解",
            "expert": "提供一则简明的资料索引",
        }[knowledge_level]
