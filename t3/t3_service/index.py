from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import Citation

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ALNUM_RE = re.compile(r"[\w]+", re.UNICODE)


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return "".join(char for char in value.strip() if not char.isspace())


def query_terms(value: str) -> list[str]:
    normalized = normalize_query(value).lower()
    terms: list[str] = []
    seen: set[str] = set()
    cjk_run: list[str] = []

    def flush_cjk() -> None:
        if len(cjk_run) == 1:
            candidates = cjk_run[:]
        else:
            candidates = ["".join(cjk_run[i : i + 2]) for i in range(len(cjk_run) - 1)]
        for term in candidates:
            if term and term not in seen:
                terms.append(term)
                seen.add(term)
        cjk_run.clear()

    for char in normalized:
        if _CJK_RE.fullmatch(char):
            cjk_run.append(char)
        else:
            flush_cjk()
    flush_cjk()
    for token in _ALNUM_RE.findall(normalized):
        token = token.lower()
        if token and token not in seen:
            terms.append(token)
            seen.add(token)
    return terms


def score_text(query: str, text: str) -> float:
    terms = query_terms(query)
    if not terms:
        return 0.0
    normalized_text = unicodedata.normalize("NFKC", text).lower()
    matched = sum(1 for term in terms if term in normalized_text)
    if not matched:
        return 0.0
    # Coverage gives a predictable 0..1 score; a full query substring receives a
    # small deterministic boost while never exceeding 1.
    score = matched / len(terms)
    compact_query = normalize_query(query).lower()
    if compact_query and compact_query in normalized_text:
        score = min(1.0, score + 0.1)
    return round(score, 6)


def retrieve(
    rows: list[dict[str, Any]],
    *,
    query: str,
    language: str | None,
    top_k: int,
    authorization_status: list[str] | None,
    max_excerpt_chars: int,
) -> list[Citation]:
    allowed = set(authorization_status or {"authorized", "public"})
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        if row["authorization_status"] not in allowed:
            continue
        if language and row.get("language") and row["language"] != language:
            continue
        score = score_text(query, row["text"])
        if score > 0:
            candidates.append((score, row))
    candidates.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
    results: list[Citation] = []
    for score, row in candidates[:top_k]:
        excerpt = row["text"][:max_excerpt_chars]
        results.append(
            Citation(
                citation_id=f"CIT-{row['chunk_id']}",
                source_id=row["source_id"],
                title=row["title"],
                section=row.get("section"),
                uri=row["source_uri"],
                excerpt=excerpt,
                score=score,
            )
        )
    return results
