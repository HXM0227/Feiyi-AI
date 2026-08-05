from __future__ import annotations

import hashlib
import re

from .config import Settings
from .dashscope_client import (
    AsrError,
    DashScopeAsrClient,
    DashScopeTtsClient,
    TtsError,
)
from .schemas import (
    InputType,
    NormalizeRequest,
    NormalizeResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)


class InputNormalizationError(ValueError):
    """Raised for an input that cannot be normalized under the T6 MVP contract."""


class AsrUnavailableError(InputNormalizationError):
    """真实 ASR 服务不可用。"""


class TtsUnavailableError(InputNormalizationError):
    """真实 TTS 服务不可用。"""


_LANGUAGE_ALIASES = {
    "auto": "auto",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
}
_CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def canonical_language(value: str) -> str:
    language = _LANGUAGE_ALIASES.get(value.strip().lower())
    if language is None:
        raise InputNormalizationError("T6 MVP 目前仅支持 auto、zh-CN 和 en 语言标记")
    return language


def detect_text_language(text: str) -> tuple[str, float]:
    chinese = len(_CHINESE_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if chinese > latin and chinese:
        return "zh-CN", min(0.99, 0.75 + chinese / max(len(text), 1))
    if latin:
        return "en", min(0.99, 0.75 + latin / max(len(text), 1))
    return "unknown", 0.0


class InputMediaService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.asr = (
            DashScopeAsrClient(settings)
            if settings.mode == "dashscope"
            else None
        )
        self.tts = (
            DashScopeTtsClient(settings)
            if settings.mode == "dashscope"
            else None
        )

    def normalize(self, request: NormalizeRequest) -> NormalizeResponse:
        source_language = canonical_language(request.source_language)
        item = request.input
        if item.type is InputType.TEXT:
            query = item.text.strip()  # validation guarantees a non-empty value
            detected, confidence = (
                detect_text_language(query)
                if source_language == "auto"
                else (source_language, 1.0)
            )
        elif item.type is InputType.AUDIO:
            if self.asr is None:
                query = self._media_query(item.type, source_language)
                detected, confidence = self._non_text_language(source_language)
            else:
                try:
                    query = self.asr.transcribe(
                        str(item.media_url),
                        source_language,
                    )
                except AsrError as exc:
                    raise AsrUnavailableError(str(exc)) from exc

                detected, confidence = (
                    detect_text_language(query)
                    if source_language == "auto"
                    else (source_language, 1.0)
                )

        elif item.type is InputType.IMAGE:
            query = self._media_query(item.type, source_language)
            detected, confidence = self._non_text_language(source_language)

        elif item.type is InputType.EXHIBIT_ID:
            exhibit_id = item.exhibit_id.strip()
            query = self._exhibit_query(exhibit_id, source_language)
            detected, confidence = self._non_text_language(source_language)
        return NormalizeResponse(
            query=query,
            detected_language=detected,
            confidence=confidence,
        )

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResponse:
        language = canonical_language(request.language)
        if language == "auto":
            language, _ = detect_text_language(request.text)
        voice = request.voice.strip() if request.voice and request.voice.strip() else None
        if self.tts is not None:
            try:
                url, selected_voice = self.tts.synthesize(request.text, language, voice)
            except TtsError as exc:
                raise TtsUnavailableError(str(exc)) from exc
            return SynthesizeResponse(
                url=url,
                mime_type="audio/wav",
                voice=selected_voice,
            )

        voice = voice or "default"
        digest = hashlib.sha256(
            f"{language}:{voice}:{request.text}".encode("utf-8")
        ).hexdigest()[:16]
        return SynthesizeResponse(
            url=f"mock://audio/{digest}.mp3",
            mime_type="audio/mpeg",
            voice=voice,
        )

    @staticmethod
    def _non_text_language(source_language: str) -> tuple[str, float]:
        if source_language == "auto":
            return "unknown", 0.0
        return source_language, 1.0

    @staticmethod
    def _exhibit_query(exhibit_id: str, source_language: str) -> str:
        if source_language == "en":
            return f"Please introduce exhibit {exhibit_id}."
        return f"请介绍展品 {exhibit_id}。"

    @staticmethod
    def _media_query(input_type: InputType, source_language: str) -> str:
        if source_language == "en":
            return f"Please identify and introduce the intangible cultural heritage content in this {input_type.value}."
        return f"请识别并介绍该{input_type.value}中的非遗内容。"
