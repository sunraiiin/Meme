import unittest
import uuid
from unittest.mock import patch

from app.core.memory.validation.identity_migration import build_identity_migration_preview
from app.services.memory_identity_migration_service import MemoryIdentityMigrationService
from app.repositories.neo4j import cypher_queries as cq


class _FakeRecord:
    id = "audit-1"
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    plan_id = "plan-1"
    operation_id = "operation-1"
    request = "migration"
    operation_kind = "migrate_canonical_self"
    risk = "high"
    status = "confirmed"
    before = {}
    after = None
    error = None
    confirmed_at = None
    executed_at = None
    created_at = None


class _FakeAuditRepository:
    def __init__(self, _session):
        self.record = _FakeRecord()

    async def get_for_user(self, _user_id, _operation_id):
        return None

    async def create_confirmed(self, **_kwargs):
        return self.record

    async def mark_executed(self, record, after):
        record.status = "executed"
        record.after = after
        return record

    async def mark_failed(self, record, error):
        record.status = "failed"
        record.error = error
        return record


class _FakeGraphRepository:
    def __init__(self):
        self.migrated = None

    async def validator_entities(self, _user_id):
        return [
            {
                "id": "self-1", "name": "林舟", "type": "生命体", "aliases": [],
                "is_active": True, "is_invalidated": False,
            },
            {
                "id": "alias-1", "name": "林舟", "type": "称呼别名", "aliases": [],
                "is_active": True, "is_invalidated": False,
            },
            {
                "id": "pet-1", "name": "多多", "type": "生命体", "aliases": [],
                "is_active": True, "is_invalidated": False,
            },
        ]

    async def validator_relations(self, _user_id):
        return [{"id": "r-1", "source_id": "self-1", "target_id": "pet-1"}]

    async def migrate_canonical_self(self, **kwargs):
        self.migrated = kwargs
        return {"canonical_entity_id": kwargs["canonical_entity_id"], "aliases_marked": 1}


class MemoryIdentityMigrationPreviewTests(unittest.TestCase):
    def test_multiple_life_entities_require_user_confirmation(self):
        preview = build_identity_migration_preview(
            user_id="user-1",
            entities=[
                {"id": "person-1", "name": "林舟", "type": "生命体"},
                {"id": "person-2", "name": "林夕", "type": "生命体"},
                {"id": "alias-1", "name": "小舟", "type": "称呼别名"},
            ],
            relations=[{"id": "r1", "source_id": "person-1", "target_id": "alias-1"}],
        )

        self.assertEqual(preview.status, "needs_user_confirmation")
        self.assertIsNone(preview.recommended_display_name)
        self.assertEqual(preview.identity_key, "self:user-1")
        self.assertEqual(preview.alias_candidates[0].relation_count, 1)


class MemoryIdentityMigrationExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_requires_explicit_confirmation(self):
        service = MemoryIdentityMigrationService(repo=_FakeGraphRepository(), session=object())
        with self.assertRaisesRegex(Exception, "明确确认"):
            await service.execute(
                uuid.UUID("00000000-0000-0000-0000-000000000001"),
                canonical_entity_id="self-1",
                alias_entity_ids=["alias-1"],
                display_name="林舟",
                confirmed=False,
            )

    async def test_execution_uses_explicit_ids_and_keeps_other_life_entity(self):
        repo = _FakeGraphRepository()
        service = MemoryIdentityMigrationService(repo=repo, session=object())
        with patch(
            "app.services.memory_identity_migration_service.MemoryCurationRepository",
            _FakeAuditRepository,
        ):
            result = await service.execute(
                uuid.UUID("00000000-0000-0000-0000-000000000001"),
                canonical_entity_id="self-1",
                alias_entity_ids=["alias-1"],
                display_name="林舟",
                confirmed=True,
            )

        self.assertEqual(result["status"], "executed")
        self.assertEqual(repo.migrated["canonical_entity_id"], "self-1")
        self.assertEqual(repo.migrated["alias_entity_ids"], ["alias-1"])
        self.assertNotIn("pet-1", repo.migrated["alias_entity_ids"])


class MemoryIdentityMigrationCypherTests(unittest.TestCase):
    def test_migration_is_explicit_and_non_destructive(self):
        self.assertIn("$canonical_entity_id", cq.IDENTITY_MIGRATION_MARK_KEEPER)
        self.assertIn("$alias_entity_ids", cq.IDENTITY_MIGRATION_MARK_KEEPER)
        self.assertIn("merged_into = $canonical_entity_id", cq.IDENTITY_MIGRATION_MARK_ALIASES)
        self.assertNotIn("DETACH DELETE", cq.IDENTITY_MIGRATION_MARK_KEEPER)
        self.assertNotIn("DETACH DELETE", cq.IDENTITY_MIGRATION_MARK_ALIASES)

    def test_single_explicit_self_is_ready_but_still_requires_confirmation(self):
        preview = build_identity_migration_preview(
            user_id="user-1",
            entities=[
                {
                    "id": "self-1",
                    "name": "林夕",
                    "type": "生命体",
                    "is_self": True,
                    "aliases": ["用户"],
                }
            ],
            relations=[],
        )

        self.assertEqual(preview.status, "ready_for_confirmation")
        self.assertEqual(preview.recommended_display_name, "林夕")
        self.assertEqual(preview.side_effects, "none")

    def test_no_candidate_never_guesses_from_unrelated_entities(self):
        preview = build_identity_migration_preview(
            user_id="user-1",
            entities=[{"id": "skill-1", "name": "Python", "type": "技能"}],
            relations=[],
        )

        self.assertEqual(preview.status, "no_candidate")
        self.assertIsNone(preview.recommended_display_name)


if __name__ == "__main__":
    unittest.main()
