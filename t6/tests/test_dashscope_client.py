from __future__ import annotations

import socket
import unittest
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch

from t6_input_media.config import Settings
from t6_input_media.dashscope_client import (
    AsrError,
    DashScopeAsrClient,
    DashScopeTtsClient,
    DashScopeVisionClient,
    TtsError,
    VisionError,
)


PUBLIC_DNS_RESULT = [
    (
        socket.AF_INET,
        socket.SOCK_STREAM,
        6,
        "",
        ("8.8.8.8", 443),
    )
]


class DashScopeAsrClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = DashScopeAsrClient(
            Settings(
                mode="dashscope",
                dashscope_api_key="test-key-not-real",
                asr_model="qwen3-asr-flash",
            )
        )

    def test_transcribe_returns_text(self) -> None:
        response = SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=[{"text": "请介绍中国剪纸"}]
                        )
                    )
                ]
            ),
        )

        with (
            patch(
                "t6_input_media.dashscope_client.socket.getaddrinfo",
                return_value=PUBLIC_DNS_RESULT,
            ),
            patch(
                "t6_input_media.dashscope_client."
                "dashscope.MultiModalConversation.call",
                return_value=response,
            ) as call,
        ):
            result = self.client.transcribe(
                "https://audio.example.org/demo.mp3",
                "zh-CN",
            )

        self.assertEqual(result, "请介绍中国剪纸")
        self.assertEqual(
            call.call_args.kwargs["model"],
            "qwen3-asr-flash",
        )
        self.assertEqual(
            call.call_args.kwargs["asr_options"]["language"],
            "zh",
        )

    def test_transcribe_repairs_utf8_mojibake(self) -> None:
        response = SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=[
                                {
                                    "text": (
                                        "Hello World\u00ef\u00bc\u008c\u00e6\u009d\u00a5"
                                        "\u00e8\u0087\u00aa\u00e9\u0098\u00bf\u00e9\u0087\u008c"
                                        "\u00e5\u00b7\u00b4\u00e5\u00b7\u00b4\u00e8\u00be\u00be"
                                        "\u00e6\u0091\u00a9\u00e9\u0099\u00a2\u00e8\u00af\u00ad"
                                        "\u00e9\u009f\u00b3\u00e5\u00ae\u009e\u00e9\u00aa\u008c"
                                        "\u00e5\u00ae\u00a4\u00e3\u0080\u0082"
                                    )
                                }
                            ]
                        )
                    )
                ]
            ),
        )

        with (
            patch(
                "t6_input_media.dashscope_client.socket.getaddrinfo",
                return_value=PUBLIC_DNS_RESULT,
            ),
            patch(
                "t6_input_media.dashscope_client."
                "dashscope.MultiModalConversation.call",
                return_value=response,
            ),
        ):
            result = self.client.transcribe(
                "https://audio.example.org/demo.mp3",
                "en",
            )

        self.assertEqual(
            result,
            "Hello World，来自阿里巴巴达摩院语音实验室。",
        )

    def test_transcribe_rejects_provider_failure(self) -> None:
        response = SimpleNamespace(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="InternalError",
            message="provider unavailable",
        )

        with (
            patch(
                "t6_input_media.dashscope_client.socket.getaddrinfo",
                return_value=PUBLIC_DNS_RESULT,
            ),
            patch(
                "t6_input_media.dashscope_client."
                "dashscope.MultiModalConversation.call",
                return_value=response,
            ),
        ):
            with self.assertRaises(AsrError):
                self.client.transcribe(
                    "https://audio.example.org/demo.mp3",
                    "auto",
                )

    def test_transcribe_rejects_private_address(self) -> None:
        private_dns_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", 443),
            )
        ]

        with patch(
            "t6_input_media.dashscope_client.socket.getaddrinfo",
            return_value=private_dns_result,
        ):
            with self.assertRaises(AsrError):
                self.client.transcribe(
                    "https://audio.example.org/demo.mp3",
                    "auto",
                )

    def test_synthesize_returns_provider_audio_url(self) -> None:
        client = DashScopeTtsClient(self.client.settings)
        response = SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                audio=SimpleNamespace(url="https://audio.example.org/result.wav")
            ),
        )

        with patch(
            "t6_input_media.dashscope_client."
            "dashscope.MultiModalConversation.call",
            return_value=response,
        ) as call:
            url, voice = client.synthesize("有据讲解", "zh-CN", None)

        self.assertEqual(url, "https://audio.example.org/result.wav")
        self.assertEqual(voice, "Cherry")
        self.assertEqual(call.call_args.kwargs["language_type"], "Chinese")

    def test_synthesize_rejects_provider_failure(self) -> None:
        client = DashScopeTtsClient(self.client.settings)
        response = SimpleNamespace(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="InternalError",
            message="provider unavailable",
        )

        with patch(
            "t6_input_media.dashscope_client."
            "dashscope.MultiModalConversation.call",
            return_value=response,
        ):
            with self.assertRaises(TtsError):
                client.synthesize("A guide", "en", "Cherry")

    def test_vision_returns_structured_query(self) -> None:
        client = DashScopeVisionClient(self.client.settings)
        response = SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=[
                                {
                                    "text": (
                                        '{"query":"请介绍图片中的剪纸纹样",'
                                        '"detected_language":"zh-CN","confidence":0.84}'
                                    )
                                }
                            ]
                        )
                    )
                ]
            ),
        )
        with patch(
            "t6_input_media.dashscope_client."
            "dashscope.MultiModalConversation.call",
            return_value=response,
        ) as call:
            result = client.identify("https://media.example.org/paper-cutting.jpg", "auto")

        self.assertEqual(result, ("请介绍图片中的剪纸纹样", "zh-CN", 0.84))
        self.assertEqual(call.call_args.kwargs["model"], "qwen3.6-flash")

    def test_vision_rejects_non_json_response(self) -> None:
        client = DashScopeVisionClient(self.client.settings)
        response = SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=[{"text": "not-json"}]))
                ]
            ),
        )
        with patch(
            "t6_input_media.dashscope_client."
            "dashscope.MultiModalConversation.call",
            return_value=response,
        ):
            with self.assertRaises(VisionError):
                client.identify("https://media.example.org/paper-cutting.jpg", "auto")


if __name__ == "__main__":
    unittest.main()
