from __future__ import annotations

import io
import json
import socket
import subprocess
import unittest
import wave
from unittest.mock import patch

import httpx
from PIL import Image

from t6_input_media.config import Settings
from t6_input_media.media import (
    MediaInspector,
    MediaDependencyError,
    MediaTooLargeError,
    MediaValidationError,
)


PUBLIC_DNS_RESULT = [
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
]


def wav_bytes(seconds: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 8000 * seconds)
    return buffer.getvalue()


def png_bytes(size: tuple[int, int] = (2, 2)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def webm_probe(
    *,
    format_name: str = "matroska,webm",
    duration: float = 1.0,
    streams: list[dict[str, str]] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps(
            {
                "format": {"format_name": format_name, "duration": str(duration)},
                "streams": streams
                if streams is not None
                else [{"codec_type": "audio", "codec_name": "opus"}],
            }
        ),
        stderr="",
    )


class MediaInspectorTests(unittest.TestCase):
    def _inspector(
        self,
        response: httpx.Response,
        **settings: object,
    ) -> MediaInspector:
        client = httpx.Client(transport=httpx.MockTransport(lambda _: response))
        defaults = {
            "mode": "dashscope",
            "dashscope_api_key": "test-key-not-real",
            "media_allowed_hosts": ("media.example.org",),
        }
        defaults.update(settings)
        return MediaInspector(Settings(**defaults), client=client)

    def test_inspects_allowed_wav_and_duration(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/wav"}, content=wav_bytes())
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            result = inspector.inspect_audio("https://media.example.org/sample.wav")
        self.assertEqual(result.mime_type, "audio/wav")
        self.assertAlmostEqual(result.duration_seconds or 0, 1.0, places=1)

    def test_inspects_allowed_webm_audio(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"webm")
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
            "t6_input_media.media.subprocess.run", return_value=webm_probe()
        ):
            result = inspector.inspect_audio("https://media.example.org/sample.webm")
        self.assertEqual(result.mime_type, "audio/webm")
        self.assertEqual(result.duration_seconds, 1.0)

    def test_keeps_existing_audio_mime_types(self) -> None:
        for mime_type in ("audio/mpeg", "audio/mp4", "audio/ogg"):
            with self.subTest(mime_type=mime_type):
                inspector = self._inspector(
                    httpx.Response(200, headers={"content-type": mime_type}, content=b"audio")
                )
                with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch.object(
                    MediaInspector, "_audio_duration", return_value=1.0
                ):
                    result = inspector.inspect_audio("https://media.example.org/sample.audio")
                self.assertEqual(result.mime_type, mime_type)

    def test_rejects_webm_content_with_non_webm_container(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"not-webm")
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
            "t6_input_media.media.subprocess.run",
            return_value=webm_probe(format_name="mp3"),
        ):
            with self.assertRaisesRegex(MediaValidationError, "不是 WebM"):
                inspector.inspect_audio("https://media.example.org/fake.webm")

    def test_rejects_webm_with_video_or_without_audio(self) -> None:
        cases = {
            "video": [
                {"codec_type": "audio", "codec_name": "opus"},
                {"codec_type": "video", "codec_name": "vp9"},
            ],
            "no_audio": [{"codec_type": "subtitle", "codec_name": "webvtt"}],
        }
        for name, streams in cases.items():
            with self.subTest(name=name):
                inspector = self._inspector(
                    httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"webm")
                )
                with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
                    "t6_input_media.media.subprocess.run",
                    return_value=webm_probe(streams=streams),
                ):
                    with self.assertRaises(MediaValidationError):
                        inspector.inspect_audio("https://media.example.org/sample.webm")

    def test_rejects_webm_over_duration_limit(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"webm"),
            max_audio_seconds=1,
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
            "t6_input_media.media.subprocess.run", return_value=webm_probe(duration=2.0)
        ):
            with self.assertRaisesRegex(MediaValidationError, "时长"):
                inspector.inspect_audio("https://media.example.org/long.webm")

    def test_webm_probe_invalid_output_is_validation_error(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"webm")
        )
        invalid = subprocess.CompletedProcess(["ffprobe"], 0, "not-json", "")
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
            "t6_input_media.media.subprocess.run", return_value=invalid
        ):
            with self.assertRaises(MediaValidationError):
                inspector.inspect_audio("https://media.example.org/invalid.webm")

    def test_webm_probe_missing_or_unavailable_is_dependency_error(self) -> None:
        for error in (FileNotFoundError(), OSError("cannot execute")):
            with self.subTest(error=type(error).__name__):
                inspector = self._inspector(
                    httpx.Response(200, headers={"content-type": "audio/webm"}, content=b"webm")
                )
                with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT), patch(
                    "t6_input_media.media.subprocess.run", side_effect=error
                ):
                    with self.assertRaises(MediaDependencyError):
                        inspector.inspect_audio("https://media.example.org/missing.webm")

    def test_rejects_non_allowlisted_host_before_download(self) -> None:
        inspector = self._inspector(httpx.Response(200, content=wav_bytes()))
        with self.assertRaisesRegex(MediaValidationError, "白名单"):
            inspector.inspect_audio("https://other.example.org/sample.wav")

    def test_rejects_redirect(self) -> None:
        inspector = self._inspector(httpx.Response(302, headers={"location": "https://other.example"}))
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            with self.assertRaisesRegex(MediaValidationError, "重定向"):
                inspector.inspect_audio("https://media.example.org/sample.wav")

    def test_rejects_declared_size_over_limit(self) -> None:
        inspector = self._inspector(
            httpx.Response(
                200,
                headers={"content-type": "audio/wav", "content-length": "999"},
                content=wav_bytes(),
            ),
            max_audio_bytes=100,
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            with self.assertRaises(MediaTooLargeError):
                inspector.inspect_audio("https://media.example.org/sample.wav")

    def test_rejects_audio_over_duration_limit(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/wav"}, content=wav_bytes(2)),
            max_audio_seconds=1,
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            with self.assertRaisesRegex(MediaValidationError, "时长"):
                inspector.inspect_audio("https://media.example.org/sample.wav")

    def test_inspects_png_and_rejects_excess_pixels(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "image/png"}, content=png_bytes()),
            max_image_pixels=1,
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            with self.assertRaisesRegex(MediaValidationError, "像素"):
                inspector.inspect_image("https://media.example.org/sample.png")

    def test_provider_audio_download_does_not_require_input_allowlist(self) -> None:
        inspector = self._inspector(
            httpx.Response(200, headers={"content-type": "audio/wav"}, content=wav_bytes()),
            tts_provider_allowed_hosts=("provider.example.org",),
        )
        with patch("t6_input_media.media.socket.getaddrinfo", return_value=PUBLIC_DNS_RESULT):
            result = inspector.download_provider_audio("http://provider.example.org/result.wav")
        self.assertEqual(result.mime_type, "audio/wav")


if __name__ == "__main__":
    unittest.main()
