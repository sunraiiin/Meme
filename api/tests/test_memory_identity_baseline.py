"""记忆身份归一化重构的基线测试。

这些测试在身份解析器落地前，明确记录当前行为和目标场景：
当前流水线会把“用户”和“林夕”保留为不同类型的实体，后续 PR 应将
该行为替换为稳定的 self 身份解析。
"""
import json
import unittest
from pathlib import Path

from app.core.memory.extraction.dedup import dedup_within_batch
from app.core.memory.graph_models import EntityNode
from app.core.memory.prompt_renderer import render_prompt
from app.repositories.neo4j import cypher_queries as cq


_IDENTITY_FIXTURE = (
    Path(__file__).parents[1] / "eval" / "fixtures" / "gold" / "memory_identity.json"
)


class MemoryIdentityBaselineTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_prompt_normalizes_first_person_to_user(self):
        prompt = render_prompt(
            "extract_statement.jinja2",
            content="我叫林夕。",
            context=None,
        )

        self.assertIn('用户自指（"我""我的""我自己"）统一改写为「用户」', prompt)

    async def test_current_dedup_keeps_user_and_name_as_separate_types(self):
        entities = [
            EntityNode(user_id="baseline", name="用户", type="生命体"),
            EntityNode(user_id="baseline", name="林夕", type="称呼别名"),
        ]

        deduped, redirect = await dedup_within_batch(object(), entities)

        self.assertEqual([entity.name for entity in deduped], ["用户", "林夕"])
        self.assertEqual(redirect, {})

    def test_current_neighbor_query_only_reads_outgoing_relations(self):
        self.assertIn("(e)-[r:RELATION]->(o:Entity)", cq.ENTITY_NEIGHBORS)
        self.assertNotIn("(e)<-[r:RELATION]-(o:Entity)", cq.ENTITY_NEIGHBORS)

    def test_identity_fixture_covers_required_ambiguity_classes(self):
        rows = json.loads(_IDENTITY_FIXTURE.read_text(encoding="utf-8"))
        scenarios = {row["scenario"] for row in rows}

        self.assertGreaterEqual(len(rows), 8)
        self.assertTrue(
            {
                "self_name",
                "explicit_self_link",
                "self_alias",
                "roleplay_or_quoted_name",
                "third_person_same_name",
                "name_change",
                "negated_identity",
                "idempotent_replay",
            }.issubset(scenarios)
        )


if __name__ == "__main__":
    unittest.main()
