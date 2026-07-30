from __future__ import annotations

import re
import unicodedata

_INLINE_SPACE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


def normalize_text(text: str) -> str:
    """Apply deterministic, non-semantic text normalization."""
    value = unicodedata.normalize("NFKC", text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in value.split("\n")]
    value = "\n".join(lines).strip()
    return _BLANK_LINES.sub("\n\n", value)
