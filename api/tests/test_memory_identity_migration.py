import unittest

from app.core.memory.validation.identity_migration import build_identity_migration_preview


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
