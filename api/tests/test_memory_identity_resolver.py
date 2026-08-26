"""稳定 self 身份解析的纯单元测试，不连接 Neo4j。"""
import unittest

from app.core.memory.extraction.identity import (
    extract_identity_signals,
    is_self_identity_question,
    normalize_entity_pool,
)
from app.core.memory.extraction.dedup import merge_with_graph
from app.core.memory.graph_models import EntityNode


class _Repo:
    def __init__(self, self_entity=None, entities_by_type=None, by_name=None):
        self.self_entity = self_entity
        self.entities_by_type = entities_by_type or []
        self.by_name = by_name or {}

    async def get_self_entity(self, user_id: str, identity_key: str):
        return self.self_entity

    async def list_entities_by_type(self, user_id: str, type_: str):
        return self.entities_by_type

    async def get_entity_by_name(self, user_id: str, name: str):
        return self.by_name.get(name)


class MemoryIdentityResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_name_question_does_not_create_identity_signal(self):
        for text in ("我叫什么名字？", "你知道我叫什么吗？", "我的姓名是什么？", "我是谁？"):
            with self.subTest(text=text):
                signals = extract_identity_signals(text)
                self.assertFalse(signals.explicit_self)
                self.assertTrue(is_self_identity_question(text))

    async def test_explicit_name_with_followup_question_remains_a_declaration(self):
        signals = extract_identity_signals("我叫林夕，你记得吗？")

        self.assertEqual(signals.current_names, ("林夕",))
        self.assertFalse(is_self_identity_question("我叫林夕，你记得吗？"))

    async def test_identity_question_does_not_hide_another_assertion(self):
        self.assertFalse(is_self_identity_question("我喜欢音乐，你知道我叫什么名字吗？"))

    async def test_corrupted_question_name_recovers_from_unique_valid_alias(self):
        existing = {
            "id": "self-existing",
            "name": "什么名字",
            "aliases": ["我", "用户", "林夕"],
            "identity_key": "self:u1",
            "is_self": True,
        }
        entity = EntityNode(user_id="u1", name="用户", type="生命体")

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(existing),
            user_id="u1",
            text="用户这个月观看了一场演出。",
            entities=[entity],
        )

        self.assertEqual(normalized[0].name, "林夕")
        self.assertNotIn("什么名字", normalized[0].aliases)
        self.assertEqual(redirect[entity.id], "self-existing")

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

    async def test_migrated_self_is_reused_while_ordinary_life_entity_stays_separate(self):
        existing = {
            "id": "self-migrated",
            "name": "林舟",
            "aliases": ["我", "用户", "本人"],
            "identity_key": "self:u1",
            "is_self": True,
        }
        self_entity = EntityNode(user_id="u1", name="林舟", type="生命体")
        ordinary_entity = EntityNode(user_id="u1", name="多多", type="生命体")

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(existing),
            user_id="u1",
            text="林舟正在开发 Meme，家里的多多很可爱。",
            entities=[self_entity, ordinary_entity],
        )

        self.assertEqual([entity.id for entity in normalized], ["self-migrated", ordinary_entity.id])
        self.assertEqual(redirect, {self_entity.id: "self-migrated"})
        self.assertEqual(sum(entity.is_self for entity in normalized), 1)
        self.assertEqual(normalized[1].name, "多多")
        self.assertFalse(normalized[1].is_self)

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

    async def test_explicit_name_reuses_legacy_life_entity_before_creating_self(self):
        legacy = {
            "id": "legacy-name",
            "name": "林夕",
            "type": "生命体",
            "aliases": [],
            "description": "旧实体",
        }
        entity = EntityNode(user_id="u1", name="用户", type="生命体")

        normalized, redirect = await normalize_entity_pool(
            repo=_Repo(by_name={"林夕": legacy}),
            user_id="u1",
            text="我叫林夕。",
            entities=[entity],
        )

        self.assertEqual(normalized[0].id, "legacy-name")
        self.assertEqual(normalized[0].name, "林夕")
        self.assertEqual(redirect[entity.id], "legacy-name")


if __name__ == "__main__":
    unittest.main()
