from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from t3.t3_service.config import Settings
from t3.t3_service.index import query_terms, retrieve, score_text
from t3.t3_service.storage import SQLiteIndex


class T3IndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "t3.db")
        self.index = SQLiteIndex(self.db_path)

    def tearDown(self) -> None:
        self.index.close()
        self.temp_dir.cleanup()

    def record(self, source_id: str, authorization_status: str = "authorized", chunks=None) -> dict:
        return {
            "source_id": source_id,
            "title": f"资料 {source_id}",
            "source_uri": f"https://example.org/{source_id}",
            "media_type": "text",
            "authorization_status": authorization_status,
            "metadata": {"language": "zh-CN", "version": "1.0"},
            "chunks": chunks or [
                {
                    "chunk_id": f"{source_id}-0001",
                    "text": "剪纸历史与代表性工艺流程。",
                    "sequence": 1,
                    "section": "历史与工艺",
                    "language": "zh-CN",
                }
            ],
        }

    def test_upsert_is_idempotent_for_duplicate_chunk_id(self) -> None:
        record = self.record("SRC-1")
        self.assertEqual(self.index.upsert([record]), 1)
        record["chunks"][0]["text"] = "更新后的剪纸历史与工艺流程。"
        self.assertEqual(self.index.upsert([record]), 1)
        self.assertEqual(self.index.count(), 1)
        self.assertEqual(self.index.all_chunks()[0]["text"], "更新后的剪纸历史与工艺流程。")

    def test_multiple_chunks_are_indexed(self) -> None:
        record = self.record(
            "SRC-2",
            chunks=[
                {"chunk_id": "SRC-2-0001", "text": "剪纸历史。", "sequence": 1, "section": "历史", "language": "zh-CN"},
                {"chunk_id": "SRC-2-0002", "text": "剪纸工艺。", "sequence": 2, "section": "工艺", "language": "zh-CN"},
            ],
        )
        self.assertEqual(self.index.upsert([record]), 2)
        self.assertEqual(self.index.count(), 2)

    def test_keyword_score_and_deterministic_order(self) -> None:
        self.index.upsert([
            self.record("SRC-B"),
            self.record("SRC-A"),
        ])
        results = retrieve(
            self.index.all_chunks(),
            query="剪纸",
            language="zh-CN",
            top_k=5,
            authorization_status=None,
            max_excerpt_chars=1000,
        )
        self.assertEqual([item.source_id for item in results], ["SRC-A", "SRC-B"])
        self.assertGreater(score_text("剪纸", "剪纸历史"), 0)
        self.assertIn("剪纸", query_terms("剪纸的历史？"))

    def test_authorization_and_explicit_filters(self) -> None:
        self.index.upsert([
            self.record("SRC-AUTH", "authorized"),
            self.record("SRC-PUBLIC", "public"),
            self.record("SRC-UNKNOWN", "unknown"),
            self.record("SRC-RESTRICTED", "restricted"),
        ])
        default_results = retrieve(
            self.index.all_chunks(), query="代表性工艺", language="zh-CN", top_k=10,
            authorization_status=None, max_excerpt_chars=1000,
        )
        self.assertEqual({item.source_id for item in default_results}, {"SRC-AUTH", "SRC-PUBLIC"})
        explicit_results = retrieve(
            self.index.all_chunks(), query="代表性工艺", language="zh-CN", top_k=10,
            authorization_status=["unknown"], max_excerpt_chars=1000,
        )
        self.assertEqual([item.source_id for item in explicit_results], ["SRC-UNKNOWN"])

    def test_no_match_is_empty(self) -> None:
        self.index.upsert([self.record("SRC-1")])
        results = retrieve(
            self.index.all_chunks(), query="不存在的词", language="zh-CN", top_k=5,
            authorization_status=None, max_excerpt_chars=1000,
        )
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
