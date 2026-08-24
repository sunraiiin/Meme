import unittest
import uuid
from unittest.mock import patch

from app.core.memory.retrieval.searcher import (
    _rank_memory_hits,
    format_memory_context,
    search_memory,
)
from app.services.memory_service import MemoryService


class MemoryReliabilityRankingTests(unittest.TestCase):
    def test_filters_entities_below_min_confidence(self):
        hits = {
            "low": {"id": "low", "name": "低置信", "confidence": 0.4, "memory_layer": "short_term"},
            "high": {"id": "high", "name": "高置信", "confidence": 0.9, "memory_layer": "short_term"},
        }
        semantic_scores = {"low": 0.95, "high": 0.7}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["high"])

    def test_high_confidence_ranks_before_low_confidence_when_semantic_score_ties(self):
        hits = {
            "low": {"id": "low", "name": "低置信", "confidence": 0.65, "memory_layer": "short_term"},
            "high": {"id": "high", "name": "高置信", "confidence": 0.95, "memory_layer": "short_term"},
        }
        semantic_scores = {"low": 0.8, "high": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["high", "low"])

    def test_long_term_ranks_before_short_term_when_score_and_confidence_tie(self):
        hits = {
            "short": {"id": "short", "name": "短期", "confidence": 0.8, "memory_layer": "short_term"},
            "long": {"id": "long", "name": "长期", "confidence": 0.8, "memory_layer": "long_term"},
        }
        semantic_scores = {"short": 0.8, "long": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=0.6,
            use_reliability_score=True,
        )

        self.assertEqual([item[0] for item in ranked], ["long", "short"])

    def test_ranked_items_keep_semantic_score_and_add_reliability_score(self):
        hits = {
            "a": {"id": "a", "name": "A", "confidence": 0.5, "memory_layer": "long_term"},
        }
        semantic_scores = {"a": 0.8}

        ranked = _rank_memory_hits(
            hits,
            semantic_scores,
            top_k=10,
            min_confidence=None,
            use_reliability_score=True,
        )

        _, score, reliability_score = ranked[0]
        self.assertEqual(score, 0.8)
        self.assertAlmostEqual(reliability_score, 0.8 * 0.5 * 1.1)


class MemoryContextFormattingTests(unittest.TestCase):
    def test_low_confidence_entity_and_relation_are_marked_uncertain(self):
        context = format_memory_context(
            [
                {
                    "name": "爵士乐",
                    "type": "兴趣",
                    "description": "用户可能喜欢爵士乐",
                    "confidence": 0.7,
                    "relations": [
                        {"predicate": "偏好", "object_name": "夜间播放列表", "confidence": 0.7}
                    ],
                }
            ]
        )

        self.assertIn("待确认", context)
        self.assertIn("爵士乐", context)
        self.assertIn("夜间播放列表", context)

    def test_high_confidence_entity_is_not_marked_uncertain(self):
        context = format_memory_context(
            [
                {
                    "name": "Python",
                    "type": "技能",
                    "description": "用户熟悉 Python",
                    "confidence": 0.9,
                    "relations": [],
                }
            ]
        )

        self.assertNotIn("待确认", context)
        self.assertIn("Python", context)

    def test_incoming_relation_keeps_original_subject_and_evidence(self):
        context = format_memory_context(
            [
                {
                    "name": "AI 应用工程",
                    "type": "职业方向",
                    "description": "",
                    "confidence": 0.95,
                    "relations": [
                        {
                            "subject_name": "林舟",
                            "predicate": "目标是",
                            "object_name": "AI 应用工程",
                            "source_text": "我希望进入 AI 应用工程方向。",
                            "confidence": 0.95,
                        }
                    ],
                }
            ]
        )

        self.assertIn("林舟 目标是 AI 应用工程", context)
        self.assertIn("依据：我希望进入 AI 应用工程方向。", context)

    def test_relation_without_source_is_explicitly_marked(self):
        context = format_memory_context(
            [
                {
                    "name": "Python",
                    "type": "技能",
                    "description": "",
                    "confidence": 0.9,
                    "relations": [
                        {"predicate": "属于", "object_name": "后端开发", "confidence": 0.9}
                    ],
                }
            ]
        )

        self.assertIn("证据缺失", context)


class MemoryProfileConfidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_includes_entity_and_relation_confidence(self):
        service = MemoryService(session=None)  # type: ignore[arg-type]
        user_id = uuid.uuid4()

        class _Repo:
            async def list_all_entities(self, user_id_text: str) -> list[dict]:
                self.user_id_text = user_id_text
                return [
                    {
                        "id": "entity-1",
                        "name": "爵士乐",
                        "type": "兴趣",
                        "description": "用户可能喜欢爵士乐",
                        "confidence": 0.7,
                        "relations": [
                            {
                                "predicate": "偏好",
                                "object_name": "夜间播放列表",
                                "object_type": "歌单",
                                "confidence": 0.65,
                            }
                        ],
                    }
                ]

            async def entity_type_counts(self, user_id_text: str) -> list[dict]:
                return [{"type": "兴趣", "cnt": 1}]

        repo = _Repo()
        service._memory_graph_repo_factory = lambda: repo

        profile = await service.get_profile(user_id)
        entity = profile["groups"][0]["entities"][0]

        self.assertEqual(entity["confidence"], 0.7)
        self.assertEqual(entity["relations"][0]["confidence"], 0.65)


class MemoryRetrievalRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fulltext_alias_hit_survives_exact_search_without_vector_hit(self):
        class _EmbedClient:
            async def embed_one(self, query: str) -> list[float]:
                return [0.1]

        class _Repo:
            async def search_entities_by_vector(self, user_id, vector, top_k):
                raise RuntimeError("vector index unavailable in unit test")

            async def search_entities_by_fulltext(self, user_id, query, top_k):
                return [
                    {
                        "id": "self-1",
                        "name": "林夕",
                        "type": "生命体",
                        "aliases": ["用户"],
                        "identity_key": "self:user-1",
                        "is_self": True,
                        "score": 0.99,
                    }
                ]

            async def bump_entity_access(self, user_id, entity_ids):
                return None

            async def get_entity_neighbors(self, user_id, entity_ids):
                return [
                    {
                        "entity_id": "self-1",
                        "subject_name": "林夕",
                        "predicate": "目标是",
                        "object_name": "AI 应用工程",
                        "source_text": "我希望进入 AI 应用工程方向。",
                        "direction": "outgoing",
                    }
                ]

        with patch(
            "app.core.memory.retrieval.searcher.MemoryGraphRepository",
            return_value=_Repo(),
        ):
            results = await search_memory(
                embed_client=_EmbedClient(),
                user_id=uuid.uuid4(),
                query="林夕",
                min_vector_score=0.8,
            )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_self"])
        self.assertEqual(results[0]["relations"][0]["subject_name"], "林夕")


if __name__ == "__main__":
    unittest.main()
