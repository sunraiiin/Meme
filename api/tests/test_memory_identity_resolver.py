"""稳定 self 身份解析的纯单元测试，不连接 Neo4j。"""
import unittest

from app.core.memory.extraction.identity import (
    extract_identity_signals,
    normalize_entity_pool,
)
from app.core.memory.extraction.dedup import merge_with_graph
from app.core.memory.graph_models import EntityNode


class _Repo:
    def __init__(self, self_entity=None, entities_by_type=None):
        self.self_entity = self_entity
        self.entities_by_type = entities_by_type or []

    async def get_self_entity(self, user_id: str, identity_key: str):
        return self.self_entity

    async def list_entities_by_type(self, user_id: str, type_: str):
        return self.entities_by_type


class MemoryIdentityResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_name_collapses_user_and_alias_into_one_self(self):
        entities = [
            EntityNode(user_id="u1", name="用户", type="生命体"),
            EntityNode(user_id="u1", name="林夕", type="称呼别名"),
        ]

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(), user_id="u1", text="我叫林夕。", entities=entities
        )

        self.assertEqual(len(normalized), 1)
        self.assertTrue(normalized[0].is_self)
        self.assertEqual(normalized[0].name, "林夕")
        self.assertEqual(set(redirect), {entities[0].id, entities[1].id})
        self.assertEqual(set(normalized[0].aliases), {"我", "用户", "本人", "自己", "我本人"})

    async def test_known_alias_resolves_bare_name_to_existing_self(self):
        existing = {
            "id": "self-existing",
            "name": "林夕",
            "aliases": ["我", "用户"],
            "description": "用户本人",
            "identity_key": "self:u1",
            "is_self": True,
            "importance": 0.8,
            "confidence": 0.9,
        }
        entity = EntityNode(user_id="u1", name="林夕", type="生命体")

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(existing), user_id="u1", text="林夕完成了项目。", entities=[entity]
        )

        self.assertEqual(normalized[0].id, "self-existing")
        self.assertEqual(redirect[entity.id], "self-existing")

    async def test_same_name_with_colleague_context_is_not_bound_to_self(self):
        existing = {
            "id": "self-existing",
            "name": "林夕",
            "aliases": ["我", "用户"],
            "identity_key": "self:u1",
            "is_self": True,
        }
        entity = EntityNode(user_id="u1", name="林夕", type="生命体")

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(existing),
            user_id="u1",
            text="我的同事林夕负责测试。",
            entities=[entity],
        )

        self.assertEqual(normalized[0].id, entity.id)
        self.assertEqual(redirect, {})

    async def test_name_change_keeps_old_name_as_alias(self):
        existing = {
            "id": "self-existing",
            "name": "林夕",
            "aliases": ["我", "用户"],
            "identity_key": "self:u1",
            "is_self": True,
        }

        signals = extract_identity_signals("我以前叫林夕，现在叫林舟。")
        self.assertEqual(signals.current_names, ("林舟",))
        self.assertIn("林夕", signals.alias_names)

        normalized, _ = await normalize_entity_pool(
            repo=_Repo(existing),
            user_id="u1",
            text="我以前叫林夕，现在叫林舟。",
            entities=[EntityNode(user_id="u1", name="用户", type="生命体")],
        )

        self.assertEqual(normalized[0].name, "林舟")
        self.assertIn("林夕", normalized[0].aliases)

    async def test_negated_name_is_not_added_as_active_alias(self):
        signals = extract_identity_signals("我不叫林夕，刚才说错了。")
        self.assertIn("林夕", signals.invalid_names)
        self.assertFalse(signals.current_names)

        normalized, _ = await normalize_entity_pool(
            repo=_Repo(),
            user_id="u1",
            text="我不叫林夕，刚才说错了。",
            entities=[EntityNode(user_id="u1", name="用户", type="生命体")],
        )

        self.assertNotIn("林夕", normalized[0].aliases)

    async def test_graph_merge_reuses_existing_self_even_when_display_name_changes(self):
        existing = {
            "id": "self-existing",
            "name": "用户",
            "type": "生命体",
            "aliases": ["我"],
            "identity_key": "self:u1",
            "is_self": True,
            "description": "用户本人",
        }
        entity = EntityNode(
            id="self:u1",
            user_id="u1",
            name="林夕",
            type="生命体",
            identity_key="self:u1",
            is_self=True,
        )

        merged, redirect = await merge_with_graph(
            object(), _Repo(entities_by_type=[existing]), "u1", [entity]
        )

        self.assertEqual(merged[0].id, "self-existing")
        self.assertEqual(merged[0].name, "林夕")
        self.assertIn("用户", merged[0].aliases)
        self.assertEqual(redirect, {"self:u1": "self-existing"})


if __name__ == "__main__":
    unittest.main()
