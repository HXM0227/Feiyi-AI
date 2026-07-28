from __future__ import annotations

import re
from collections.abc import Iterable

from .normalizer import normalize_text

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.!?])\s+(?=[A-Z0-9\u4e00-\u9fff])")


def _split_long_unit(unit: str, max_chars: int) -> list[str]:
    return [unit[start : start + max_chars] for start in range(0, len(unit), max_chars)]


def _units(text: str, max_chars: int) -> Iterable[str]:
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            yield paragraph
            continue
        sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
        for sentence in sentences or [paragraph]:
            if len(sentence) <= max_chars:
                yield sentence
            else:
                yield from _split_long_unit(sentence, max_chars)


def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 100) -> list[str]:
    """Split text deterministically, preferring paragraph and sentence boundaries."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and smaller than max_chars")
    normalized = normalize_text(text)
    if not normalized:
        return []

    result: list[str] = []
    current = ""
    for unit in _units(normalized, max_chars):
        if not current:
            current = unit
            continue
        candidate = f"{current}\n{unit}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        result.append(current)
        tail = current[-overlap:] if overlap else ""
        candidate = f"{tail}\n{unit}" if tail else unit
        current = candidate if len(candidate) <= max_chars else unit
    if current:
        result.append(current)
    return [item.strip() for item in result if item.strip()]
