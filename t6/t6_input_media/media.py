from __future__ import annotations

import io
import ipaddress
import json
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from mutagen import File as MutagenFile
from PIL import Image, UnidentifiedImageError

from .config import Settings


class MediaValidationError(ValueError):
    """媒体地址或媒体内容不符合 T6 输入安全边界。"""


class MediaTooLargeError(MediaValidationError):
    """媒体内容超过已配置的输入上限。"""


class MediaDependencyError(RuntimeError):
    """媒体校验所需的本机依赖不可用。"""


@dataclass(frozen=True, slots=True)
class ValidatedMedia:
    source_url: str
    mime_type: str
    data: bytes
    duration_seconds: float | None = None


_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/webm",
}
_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class MediaInspector:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client

    def inspect_audio(self, media_url: str) -> ValidatedMedia:
        result = self._download(
            media_url,
            allowed_mime_types=_AUDIO_MIME_TYPES,
            max_bytes=self.settings.max_audio_bytes,
            enforce_allowlist=True,
        )
        duration = (
            self._webm_audio_duration(result.data)
            if result.mime_type == "audio/webm"
            else self._audio_duration(result.data)
        )
        if duration > self.settings.max_audio_seconds:
            raise MediaValidationError(
                f"音频时长超过 {self.settings.max_audio_seconds} 秒上限"
            )
        return ValidatedMedia(
            source_url=result.source_url,
            mime_type=result.mime_type,
            data=result.data,
            duration_seconds=duration,
        )

    def inspect_image(self, media_url: str) -> ValidatedMedia:
        result = self._download(
            media_url,
            allowed_mime_types=_IMAGE_MIME_TYPES,
            max_bytes=self.settings.max_image_bytes,
            enforce_allowlist=True,
        )
        try:
            with Image.open(io.BytesIO(result.data)) as image:
                image.verify()
            with Image.open(io.BytesIO(result.data)) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError) as exc:
            raise MediaValidationError("图片内容无效或与声明类型不一致") from exc
        if width * height > self.settings.max_image_pixels:
            raise MediaValidationError(
                f"图片像素超过 {self.settings.max_image_pixels} 上限"
            )
        return result

    def download_provider_audio(self, media_url: str) -> ValidatedMedia:
        """下载模型刚返回的临时音频资产；不使用输入来源白名单。"""
        result = self._download(
            media_url,
            allowed_mime_types={"audio/wav", "audio/x-wav"},
            max_bytes=self.settings.max_audio_bytes,
            enforce_allowlist=True,
            allowed_hosts=self.settings.tts_provider_allowed_hosts,
            allowed_schemes={"http", "https"},
        )
        self._audio_duration(result.data)
        return result

    def _download(
        self,
        media_url: str,
        *,
        allowed_mime_types: set[str],
        max_bytes: int,
        enforce_allowlist: bool,
        allowed_hosts: tuple[str, ...] | None = None,
        allowed_schemes: set[str] | None = None,
    ) -> ValidatedMedia:
        self._validate_url(
            media_url,
            enforce_allowlist=enforce_allowlist,
            allowed_hosts=allowed_hosts,
            allowed_schemes=allowed_schemes,
        )
        client = self._client or httpx.Client(
            timeout=self.settings.media_download_timeout_seconds,
            follow_redirects=False,
        )
        owns_client = self._client is None
        try:
            with client.stream("GET", media_url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise MediaValidationError("媒体地址不允许重定向")
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise MediaTooLargeError(f"媒体大小超过 {max_bytes} 字节上限")
                data = self._read_limited(response.iter_bytes(), max_bytes)
                mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        except httpx.HTTPError as exc:
            raise MediaValidationError("媒体地址不可访问") from exc
        finally:
            if owns_client:
                client.close()

        if mime_type not in allowed_mime_types:
            raise MediaValidationError("媒体 MIME 类型不受支持")
        return ValidatedMedia(source_url=media_url, mime_type=mime_type, data=data)

    @staticmethod
    def _read_limited(chunks: Iterable[bytes], max_bytes: int) -> bytes:
        payload = bytearray()
        for chunk in chunks:
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise MediaTooLargeError(f"媒体大小超过 {max_bytes} 字节上限")
        if not payload:
            raise MediaValidationError("媒体内容为空")
        return bytes(payload)

    def _validate_url(
        self,
        media_url: str,
        *,
        enforce_allowlist: bool,
        allowed_hosts: tuple[str, ...] | None = None,
        allowed_schemes: set[str] | None = None,
    ) -> None:
        parsed = urlparse(media_url)
        allowed_schemes = allowed_schemes or {"https"}
        if (
            parsed.scheme not in allowed_schemes
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise MediaValidationError("真实媒体仅接受公开 HTTPS URL")
        hostname = parsed.hostname.lower()
        if hostname == "localhost":
            raise MediaValidationError("禁止使用 localhost 作为媒体地址")
        if enforce_allowlist:
            hosts = allowed_hosts if allowed_hosts is not None else self.settings.media_allowed_hosts
            if not hosts:
                raise MediaValidationError("真实媒体未配置 T6_MEDIA_ALLOWED_HOSTS 白名单")
            if not any(self._host_matches(hostname, rule) for rule in hosts):
                raise MediaValidationError("媒体地址不在 T6 域名白名单中")

        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname, 443, type=socket.SOCK_STREAM
                )
            }
        except socket.gaierror as exc:
            raise MediaValidationError("媒体地址无法解析") from exc
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
                raise MediaValidationError("媒体地址不能指向内网或保留地址")

    @staticmethod
    def _host_matches(hostname: str, rule: str) -> bool:
        rule = rule.lower()
        if rule.startswith("*."):
            return hostname.endswith(rule[1:]) and hostname != rule[2:]
        return hostname == rule

    @staticmethod
    def _audio_duration(data: bytes) -> float:
        try:
            audio = MutagenFile(io.BytesIO(data))
            duration = getattr(getattr(audio, "info", None), "length", None)
        except Exception as exc:  # mutagen raises different parser-specific errors
            raise MediaValidationError("音频内容无效或与声明类型不一致") from exc
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise MediaValidationError("无法读取音频时长")
        return float(duration)

    def _webm_audio_duration(self, data: bytes) -> float:
        """使用 ffprobe 验证 WebM 容器、音频轨与时长。"""
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as output:
                output.write(data)
                temporary_path = output.name
            result = subprocess.run(
                [
                    self.settings.ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name,duration:stream=codec_type,codec_name",
                    "-of",
                    "json",
                    temporary_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            raise MediaDependencyError(
                "WebM 校验依赖 ffprobe 不可用或执行失败；请安装 FFmpeg 并配置 T6_FFPROBE_PATH"
            ) from exc
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

        if result.returncode != 0:
            raise MediaValidationError("WebM 内容无效或无法由 ffprobe 解析")
        try:
            probe = json.loads(result.stdout)
            format_name = str(probe["format"]["format_name"])
            duration = float(probe["format"]["duration"])
            streams = probe["streams"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaValidationError("WebM 内容无效或无法读取时长") from exc

        if "webm" not in {item.strip() for item in format_name.split(",")}:
            raise MediaValidationError("音频内容不是 WebM 容器")
        if any(stream.get("codec_type") == "video" for stream in streams):
            raise MediaValidationError("WebM 音频不能包含视频轨")
        audio_streams = [
            stream
            for stream in streams
            if stream.get("codec_type") == "audio"
        ]
        if not audio_streams:
            raise MediaValidationError("WebM 缺少音频轨")
        if any(stream.get("codec_name") not in {"opus", "vorbis"} for stream in audio_streams):
            raise MediaValidationError("WebM 音频编码仅支持 Opus 或 Vorbis")
        if duration <= 0:
            raise MediaValidationError("无法读取 WebM 音频时长")
        return duration
