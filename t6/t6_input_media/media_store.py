from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings
from .media import MediaInspector, ValidatedMedia


@dataclass(frozen=True, slots=True)
class StoredAudio:
    url: str
    mime_type: str


class MediaStore(Protocol):
    def store_tts_audio(self, source_url: str) -> StoredAudio: ...


class LocalMediaStore:
    def __init__(self, settings: Settings, inspector: MediaInspector) -> None:
        self.settings = settings
        self.inspector = inspector
        self.settings.media_dir.mkdir(parents=True, exist_ok=True)

    def store_tts_audio(self, source_url: str) -> StoredAudio:
        self._cleanup_expired()
        asset = self.inspector.download_provider_audio(source_url)
        filename = f"{uuid.uuid4().hex}.wav"
        target = self.settings.media_dir / filename
        temporary = target.with_suffix(".tmp")
        try:
            temporary.write_bytes(asset.data)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return StoredAudio(
            url=f"{self.settings.public_base_url}/media/audio/{filename}",
            mime_type=self._normalise_wav_mime(asset),
        )

    def _cleanup_expired(self) -> None:
        deadline = time.time() - self.settings.media_retention_hours * 3600
        for candidate in self.settings.media_dir.glob("*.wav"):
            try:
                if candidate.stat().st_mtime < deadline:
                    candidate.unlink()
            except FileNotFoundError:
                continue

    @staticmethod
    def _normalise_wav_mime(asset: ValidatedMedia) -> str:
        return "audio/wav" if asset.mime_type in {"audio/wav", "audio/x-wav"} else asset.mime_type
