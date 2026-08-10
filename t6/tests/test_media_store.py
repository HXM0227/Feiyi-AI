from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from t6_input_media.config import Settings
from t6_input_media.media import ValidatedMedia
from t6_input_media.media_store import LocalMediaStore


class FakeInspector:
    def download_provider_audio(self, _: str) -> ValidatedMedia:
        return ValidatedMedia("https://provider.example/result.wav", "audio/wav", b"RIFFtest")


class LocalMediaStoreTests(unittest.TestCase):
    def test_stores_audio_and_removes_expired_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            media_dir = Path(temporary)
            expired = media_dir / "expired.wav"
            expired.write_bytes(b"old")
            old = time.time() - 7200
            expired.touch()
            __import__("os").utime(expired, (old, old))
            store = LocalMediaStore(
                Settings(
                    mode="dashscope",
                    dashscope_api_key="test-key-not-real",
                    media_dir=media_dir,
                    public_base_url="http://127.0.0.1:8106",
                    media_retention_hours=1,
                ),
                FakeInspector(),  # type: ignore[arg-type]
            )
            asset = store.store_tts_audio("https://provider.example/result.wav")

            self.assertFalse(expired.exists())
            self.assertTrue(asset.url.startswith("http://127.0.0.1:8106/media/audio/"))
            self.assertEqual(asset.mime_type, "audio/wav")
            self.assertEqual(len(list(media_dir.glob("*.wav"))), 1)


if __name__ == "__main__":
    unittest.main()
