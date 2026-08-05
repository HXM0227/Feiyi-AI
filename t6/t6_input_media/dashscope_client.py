from __future__ import annotations

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
