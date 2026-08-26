import unittest
import uuid
import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.memory.curation.models import CurationOperation, CurationPlan
from app.core.memory.curation.semantic_planner import build_semantic_curation_plan
from app.core.memory.curation.planner import build_curation_plan
from app.core.exceptions import BizError
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
        self.assertFalse(plan.executable)


class MemoryCurationSemanticPlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_candidate_is_normalized_to_server_risk_policy(self):
        class _Client:
            async def chat(self, messages, temperature, max_tokens):
                return """{
                    "status": "ready",
                    "message": "用户希望增加称呼",
                    "operation": {
                        "kind": "add_self_alias",
                        "target_name": null,
                        "secondary_target_name": null,
                        "value": "小舟",
                        "reason": "用户明确说这是另一个称呼"
                    }
                }"""

        plan = await build_semantic_curation_plan(
            _Client(), "请把小舟作为我的另一个称呼"
        )

        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.planner_source, "llm")
        self.assertEqual(plan.operations[0].kind, "add_self_alias")
        self.assertEqual(plan.operations[0].patch, {"alias": "小舟"})
        self.assertEqual(plan.operations[0].risk, "low")
        self.assertFalse(plan.requires_confirmation)

    async def test_semantic_candidate_cannot_smuggle_target_id(self):
        class _Client:
            async def chat(self, messages, temperature, max_tokens):
                return """{
                    "status": "ready",
                    "message": "尝试注入实体 ID",
                    "operation": {
                        "kind": "invalidate_fact",
                        "target_name": "林舟",
                        "secondary_target_name": null,
                        "value": null,
                        "reason": "测试",
                        "target_id": "other-user-entity"
                    }
                }"""

        plan = await build_semantic_curation_plan(_Client(), "忘掉关于林舟的记忆")

        self.assertEqual(plan.status, "rejected")
        self.assertFalse(plan.executable)
        self.assertEqual(plan.operations, [])


class MemoryCurationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rule_plan_does_not_call_llm(self):
        class _Repo:
            async def get_self_entity(self, user_id_text, identity_key):
                return None

        resolver = AsyncMock()
        with patch(
            "app.services.memory_curation_service.get_optional_client_for_type",
            resolver,
        ):
            plan = await MemoryCurationService(
                repo=_Repo(), session=object()
            ).plan(uuid.uuid4(), "给我添加别名 小夕")

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["planner_source"], "rules")
        resolver.assert_not_awaited()

    async def test_rejected_rule_request_can_use_semantic_fallback(self):
        class _Repo:
            async def get_self_entity(self, user_id_text, identity_key):
                return {
                    "id": "self-1",
                    "name": "林舟",
                    "aliases": ["用户"],
                    "identity_key": identity_key,
                    "is_self": True,
                }

        semantic_plan = CurationPlan(
            request="请把小舟作为我的另一个称呼",
            status="ready",
            message="已理解",
            planner_source="llm",
            operations=[
                CurationOperation(
                    kind="add_self_alias",
                    summary="增加个人身份别名「小舟」",
                    risk="low",
                    requires_confirmation=False,
                    patch={"alias": "小舟"},
                )
            ],
        )
        with (
            patch(
                "app.services.memory_curation_service.get_optional_client_for_type",
                AsyncMock(return_value=object()),
            ),
            patch(
                "app.services.memory_curation_service.build_semantic_curation_plan",
                AsyncMock(return_value=semantic_plan),
            ),
        ):
            plan = await MemoryCurationService(
                repo=_Repo(), session=object()
            ).plan(uuid.uuid4(), semantic_plan.request)

        self.assertEqual(plan["planner_source"], "llm")
        self.assertEqual(plan["operations"][0]["target_id"], "self-1")
        self.assertTrue(plan["confirmation_token"])
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

    async def test_execute_requires_confirmation_and_can_be_undone(self):
        user_id = uuid.uuid4()

        class _GraphRepo:
            def __init__(self):
                self.entity = {
                    "id": "self-1",
                    "name": "旧名字",
                    "type": "生命体",
                    "description": "当前用户本人",
                    "aliases": ["用户"],
                    "identity_key": f"self:{user_id}",
                    "is_self": True,
                    "is_active": True,
                    "is_invalidated": False,
                }

            async def get_self_entity(self, user_id_text, identity_key):
                return dict(self.entity)

            async def entity_snapshot(self, user_id_text, entity_id):
                return dict(self.entity) if entity_id == self.entity["id"] else None

            async def correct_entity(self, user_id_text, entity_id, **changes):
                for key, value in changes.items():
                    if value is not None and key != "type_":
                        self.entity[key if key != "type_" else "type"] = value
                return {"id": self.entity["id"], "name": self.entity["name"]}

        class _AuditRepo:
            records = {}

            def __init__(self, session):
                self.session = session

            async def get_for_user(self, user_id_text, operation_id):
                return self.records.get(operation_id)

            async def create_confirmed(self, **kwargs):
                record = SimpleNamespace(
                    id=uuid.uuid4(),
                    user_id=kwargs["user_id"],
                    plan_id=kwargs["plan_id"],
                    operation_id=kwargs["operation_id"],
                    request=kwargs["request"],
                    operation_kind=kwargs["operation_kind"],
                    risk=kwargs["risk"],
                    requires_confirmation=kwargs["requires_confirmation"],
                    status="confirmed",
                    before=kwargs["before"],
                    after=None,
                    error=None,
                    confirmed_at=datetime.now(timezone.utc),
                    executed_at=None,
                    undone_at=None,
                    created_at=datetime.now(timezone.utc),
                )
                self.records[kwargs["operation_id"]] = record
                return record

            async def mark_executed(self, record, after):
                record.status = "executed"
                record.after = after
                record.executed_at = datetime.now(timezone.utc)
                return record

            async def mark_undone(self, record):
                record.status = "undone"
                record.undone_at = datetime.now(timezone.utc)
                return record

        graph_repo = _GraphRepo()
        service = MemoryCurationService(repo=graph_repo, session=object())
        plan = await service.plan(user_id, "我叫林夕")

        with patch(
            "app.services.memory_curation_service.MemoryCurationRepository", _AuditRepo
        ):
            tampered = copy.deepcopy(plan)
            tampered["operations"][0]["patch"]["name"] = "恶意修改"
            with self.assertRaises(BizError):
                await service.execute(
                    user_id, tampered, plan["confirmation_token"], confirmed=True
                )
            with self.assertRaises(BizError):
                await service.execute(
                    user_id, plan, plan["confirmation_token"], confirmed=False
                )
            executed = await service.execute(
                user_id, plan, plan["confirmation_token"], confirmed=True
            )
            self.assertEqual(executed["status"], "executed")
            self.assertEqual(graph_repo.entity["name"], "林夕")
            replayed = await service.execute(
                user_id, plan, plan["confirmation_token"], confirmed=True
            )
            self.assertEqual(replayed["operations"][0]["status"], "executed")
            self.assertEqual(graph_repo.entity["name"], "林夕")
            undone = await service.undo(user_id, plan["operations"][0]["operation_id"])

        self.assertEqual(undone["status"], "undone")
        self.assertEqual(graph_repo.entity["name"], "旧名字")


if __name__ == "__main__":
    unittest.main()
