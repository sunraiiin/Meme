import unittest
import uuid

from app.core.memory.curation.planner import build_curation_plan
from app.services.memory_curation_service import MemoryCurationService


class MemoryCurationPlannerTests(unittest.TestCase):
    def test_self_name_request_creates_confirmation_plan_without_cypher(self):
        plan = build_curation_plan("我叫林夕")

        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.operations[0].kind, "set_self_display_name")
        self.assertEqual(plan.operations[0].patch, {"name": "林夕"})
        self.assertTrue(plan.requires_confirmation)
        self.assertEqual(plan.side_effects, "none")

    def test_alias_request_is_low_risk_and_idempotent_candidate(self):
        plan = build_curation_plan("给我添加别名 小夕")

        self.assertEqual(plan.operations[0].kind, "add_self_alias")
        self.assertEqual(plan.operations[0].patch["alias"], "小夕")
        self.assertFalse(plan.requires_confirmation)

    def test_merge_is_high_risk(self):
        plan = build_curation_plan("合并 林夕 和 林舟")

        self.assertEqual(plan.operations[0].kind, "merge_entities")
        self.assertEqual(plan.risk, "high")
        self.assertTrue(plan.requires_confirmation)

    def test_ambiguous_or_negated_identity_is_rejected(self):
        plan = build_curation_plan("我不叫林夕")

        self.assertEqual(plan.status, "rejected")
        self.assertEqual(plan.operations, [])
        self.assertEqual(plan.side_effects, "none")

    def test_unsupported_request_is_rejected_instead_of_guessing(self):
        plan = build_curation_plan("把所有记忆整理得更智能")

        self.assertEqual(plan.status, "rejected")
        self.assertIn("暂不支持", plan.message)


class MemoryCurationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_enriches_targets_without_mutating_repository(self):
        user_id = uuid.uuid4()

        class _Repo:
            def __init__(self):
                self.mutations = 0

            async def get_self_entity(self, user_id_text, identity_key):
                return {
                    "id": "self-1",
                    "name": "林夕",
                    "type": "生命体",
                    "aliases": ["用户"],
                    "identity_key": identity_key,
                    "is_self": True,
                }

            async def get_entity_by_name(self, user_id_text, name):
                return {
                    "id": f"entity-{name}",
                    "name": name,
                    "type": "实体",
                    "description": "已有实体",
                    "aliases": [],
                }

            async def delete_entity(self, *args, **kwargs):
                self.mutations += 1

        repo = _Repo()
        plan = await MemoryCurationService(repo).plan(user_id, "合并 林夕 和 林舟")

        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["executable"])
        operation = plan["operations"][0]
        self.assertEqual(operation["target_id"], "entity-林夕")
        self.assertEqual(operation["secondary_target_id"], "entity-林舟")
        self.assertEqual(operation["target_snapshot"]["name"], "林夕")
        self.assertEqual(repo.mutations, 0)

    async def test_missing_merge_target_is_blocked(self):
        class _Repo:
            async def get_self_entity(self, user_id_text, identity_key):
                return None

            async def get_entity_by_name(self, user_id_text, name):
                return None if name == "不存在" else {"id": "entity-1", "name": name}

        plan = await MemoryCurationService(_Repo()).plan(
            uuid.uuid4(), "合并 林夕 和 不存在"
        )

        self.assertFalse(plan["executable"])
        self.assertTrue(any("不存在" in item for item in plan["blocking_reasons"]))


if __name__ == "__main__":
    unittest.main()
