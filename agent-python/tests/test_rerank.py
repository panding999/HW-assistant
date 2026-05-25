import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent_runtime import search_materials


class RerankCollection:
    def __init__(self):
        self.n_results = None

    def query(self, query_embeddings, n_results, include):
        self.n_results = n_results
        return {
            "ids": [["doc-a", "doc-b", "doc-c"]],
            "documents": [["alpha", "beta target", "gamma"]],
            "metadatas": [
                [
                    {"material_id": 1, "filename": "a.md", "section_title": "A"},
                    {"material_id": 2, "filename": "b.md", "section_title": "B"},
                    {"material_id": 3, "filename": "c.md", "section_title": "C"},
                ]
            ],
            "distances": [[0.1, 0.9, 0.6]],
        }


def fake_embed(texts):
    return [[1.0] for _ in texts]


class RerankSearchTests(unittest.TestCase):
    def test_enabled_rerank_expands_candidates_and_reorders_evidence(self):
        collection = RerankCollection()

        def fake_rerank(query_text, evidence):
            self.assertIn("target query", query_text)
            by_id = {item.chunk_id: item for item in evidence}
            by_id["doc-b"].rerank_score = 0.99
            by_id["doc-b"].rerank_model = "qwen3-rerank"
            by_id["doc-a"].rerank_score = 0.10
            by_id["doc-c"].rerank_score = 0.20
            return [by_id["doc-b"], by_id["doc-c"], by_id["doc-a"]]

        with patch.dict(
            os.environ,
            {"RERANK_ENABLED": "true", "RERANK_CANDIDATE_MULTIPLIER": "6"},
            clear=False,
        ), patch("app.agent_runtime.rerank_evidence", side_effect=fake_rerank):
            result = search_materials(collection, "target query", 2, fake_embed)

        self.assertEqual(collection.n_results, 12)
        self.assertEqual([item.chunk_id for item in result.evidence], ["doc-b", "doc-c"])
        self.assertTrue(result.rerank_enabled)
        self.assertTrue(result.rerank_applied)
        self.assertEqual(result.rerank_candidates, 3)
        self.assertEqual(result.evidence[0].rerank_score, 0.99)

    def test_rerank_failure_falls_back_to_hybrid_order(self):
        collection = RerankCollection()

        with patch.dict(os.environ, {"RERANK_ENABLED": "true"}, clear=False), patch(
            "app.agent_runtime.rerank_evidence", side_effect=RuntimeError("rerank unavailable")
        ):
            result = search_materials(collection, "target query", 2, fake_embed)

        self.assertEqual([item.chunk_id for item in result.evidence], ["doc-a", "doc-b"])
        self.assertTrue(result.rerank_enabled)
        self.assertFalse(result.rerank_applied)
        self.assertIn("rerank unavailable", result.rerank_failed_reason)


if __name__ == "__main__":
    unittest.main()
