from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from t1.t1_service.ledger import Ledger
from t1.t1_service.models import KnowledgeDocument
from t1.t1_service.chunker import chunk_text
from t1.t1_service.normalizer import normalize_text
from t1.t1_service.processor import normalize_document


class NormalizerTests(unittest.TestCase):
    def test_text_normalization_is_non_semantic_and_deterministic(self) -> None:
        raw = "  第一段\r\n\r\n\t第二段   \n\n"
        self.assertEqual(normalize_text(raw), "第一段\n\n第二段")
        self.assertEqual(chunk_text(raw, max_chars=4, overlap=1), chunk_text(raw, max_chars=4, overlap=1))

    def test_chunks_are_bounded_and_non_empty(self) -> None:
        text = "第一句。第二句。第三句。" * 20
        chunks = chunk_text(text, max_chars=20, overlap=3)
        self.assertTrue(chunks)
        self.assertTrue(all(0 < len(chunk) <= 20 for chunk in chunks))

    def test_missing_text_is_rejected_without_fabrication(self) -> None:
        doc = KnowledgeDocument(
            source_id="SRC-1",
            source_uri="https://example.org/1",
            media_type="text",
            title="示例",
            authorization_status="authorized",
            metadata={},
        )
        record, rejected, cleaned, _ = normalize_document(doc, max_chunk_chars=800, chunk_overlap=100, publish=False)
        self.assertIsNone(record)
        self.assertEqual(rejected.code, "MISSING_TEXT")
        self.assertIsNone(cleaned)

    def test_restricted_status_is_preserved(self) -> None:
        doc = KnowledgeDocument(
            source_id="SRC-2",
            source_uri="https://example.org/2",
            media_type="text",
            title="受限示例",
            authorization_status="restricted",
            metadata={"text": "真实内容", "language": "zh-CN"},
        )
        record, rejected, _, warning = normalize_document(doc, max_chunk_chars=800, chunk_overlap=100, publish=False)
        self.assertIsNone(rejected)
        self.assertEqual(record.authorization_status, "restricted")
        self.assertIn("restricted", warning)


class LedgerTests(unittest.TestCase):
    def test_upsert_keeps_one_source_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "t1.db")
            ledger = Ledger(path)
            ledger.check_ready()
            kwargs = dict(
                source_id="SRC-1",
                source_uri="https://example.org/1",
                title="示例",
                media_type="text",
                authorization_status="authorized",
                metadata={"language": "zh-CN"},
                content="内容",
                chunk_count=1,
                publish=False,
                trace_id="trace-1",
                request_id="request-1",
            )
            ledger.upsert(**kwargs)
            ledger.upsert(**{**kwargs, "title": "更新后的示例", "content": "新内容"})
            rows = ledger.list_sources()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "更新后的示例")


if __name__ == "__main__":
    unittest.main()
