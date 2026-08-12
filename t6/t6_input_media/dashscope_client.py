from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

import dashscope
import ipaddress
import socket

from .config import Settings


class AsrError(RuntimeError):
    """DashScope ASR 调用失败或未返回有效转写文本。"""


class TtsError(RuntimeError):
    """DashScope TTS 调用失败或未返回有效音频 URL。"""


class VisionError(RuntimeError):
    """DashScope 图片理解调用失败或未返回有效结构化结果。"""


class DashScopeAsrClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, media_url: str, source_language: str) -> str:
        self._validate_public_https_url(media_url)

        dashscope.base_http_api_url = self.settings.dashscope_base_http_api_url

        asr_options: dict[str, Any] = {"enable_itn": False}
        language_map = {
            "zh": "zh",
            "zh-CN": "zh",
            "en": "en",
        }
        language = language_map.get(source_language)
        if language:
            asr_options["language"] = language

        response = dashscope.MultiModalConversation.call(
            api_key=self.settings.dashscope_api_key,
            model=self.settings.asr_model,
            messages=[
                {
                    "role": "user",
                    "content": [{"audio": media_url}],
                }
            ],
            result_format="message",
            asr_options=asr_options,
        )

        if getattr(response, "status_code", None) != HTTPStatus.OK:
            code = getattr(response, "code", "UNKNOWN")
            message = getattr(response, "message", "DashScope ASR 调用失败")
            raise AsrError(f"ASR 调用失败：{code} - {message}")

        text = self._repair_utf8_mojibake(
            self._extract_text(response)
        )
        if not text:
            raise AsrError("ASR 未返回有效转写文本")
        return text

    @staticmethod
    def _validate_public_https_url(media_url: str) -> None:
        parsed = urlparse(media_url)

        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise AsrError("真实 ASR 仅接受公开 HTTPS 音频 URL")

        hostname = parsed.hostname.lower()
        if hostname == "localhost":
            raise AsrError("禁止使用 localhost 作为音频地址")

        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    443,
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise AsrError("音频地址无法解析") from exc

        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise AsrError("音频地址不能指向内网或保留地址")

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            content = response.output.choices[0].message.content
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise AsrError("ASR 响应结构不符合预期") from exc

        if isinstance(content, str):
            return content.strip()

        texts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
            else:
                value = getattr(item, "text", None)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())

        return DashScopeAsrClient._repair_utf8_mojibake(
            "".join(texts)
        )

    @staticmethod
    def _repair_utf8_mojibake(value: str) -> str:
        markers = ("Ã", "Â", "â", "ï", "ð", "æ", "è", "é")
        if not any(marker in value for marker in markers):
            return value

        try:
            return value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value


class DashScopeTtsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, text: str, language: str, voice: str | None) -> tuple[str, str]:
        if len(text) > 600:
            raise TtsError("真实 TTS 单次文本不能超过 600 个字符")

        dashscope.base_http_api_url = self.settings.dashscope_base_http_api_url
        selected_voice = voice or self.settings.tts_voice
        response = dashscope.MultiModalConversation.call(
            api_key=self.settings.dashscope_api_key,
            model=self.settings.tts_model,
            text=text,
            voice=selected_voice,
            language_type=self._language_type(language),
        )

        if getattr(response, "status_code", None) != HTTPStatus.OK:
            code = getattr(response, "code", "UNKNOWN")
            message = getattr(response, "message", "DashScope TTS 调用失败")
            raise TtsError(f"TTS 调用失败：{code} - {message}")

        audio = self._field(self._field(response, "output"), "audio")
        url = self._field(audio, "url")
        if not isinstance(url, str) or not url.strip():
            raise TtsError("TTS 未返回有效音频 URL")
        return url, selected_voice

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    @staticmethod
    def _language_type(language: str) -> str:
        return {"zh-CN": "Chinese", "en": "English"}.get(language, "Auto")


class DashScopeVisionClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def identify(self, media_url: str, source_language: str) -> tuple[str, str, float]:
        dashscope.base_http_api_url = self.settings.dashscope_base_http_api_url
        requested_language = "自动判断" if source_language == "auto" else source_language
        response = dashscope.MultiModalConversation.call(
            api_key=self.settings.dashscope_api_key,
            model=self.settings.vision_model,
            messages=[
                {
                    "role": "system",
                    "content": [
                        {
                            "text": (
                                "你是非遗导览的图片输入助手。只能根据图片中可见的物件、"
                                "文字、工艺、图案或场景生成检索线索；不能把不确定的展品"
                                "名称、年代、地域或历史事实写成确定结论。"
                                "只返回 JSON 对象，字段必须为 query、detected_language、confidence。"
                                "query 为不超过 200 字的检索问题；detected_language 只能是 zh-CN、en 或 unknown；"
                                "confidence 为 0 到 1 的数字。"
                            )
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"image": media_url},
                        {
                            "text": (
                                f"请识别此图片可用于检索的非遗导览线索。用户指定语言：{requested_language}。"
                            )
                        },
                    ],
                },
            ],
            result_format="message",
        )
        if getattr(response, "status_code", None) != HTTPStatus.OK:
            code = getattr(response, "code", "UNKNOWN")
            message = getattr(response, "message", "DashScope 图片理解调用失败")
            raise VisionError(f"图片理解调用失败：{code} - {message}")

        raw = DashScopeAsrClient._extract_text(response)
        parsed = self._parse_json(raw)
        query = parsed.get("query")
        language = parsed.get("detected_language")
        confidence = parsed.get("confidence")
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise VisionError("图片理解未返回有效 query")
        if language not in {"zh-CN", "en", "unknown"}:
            raise VisionError("图片理解返回的 detected_language 不受支持")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise VisionError("图片理解返回的 confidence 无效")
        if not 0 <= float(confidence) <= 1:
            raise VisionError("图片理解返回的 confidence 超出范围")
        return query.strip(), language, float(confidence)

    @staticmethod
    def _parse_json(value: str) -> dict[str, Any]:
        candidate = value.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise VisionError("图片理解响应不是有效 JSON") from exc
        if not isinstance(parsed, dict):
            raise VisionError("图片理解响应必须是 JSON 对象")
        return parsed
