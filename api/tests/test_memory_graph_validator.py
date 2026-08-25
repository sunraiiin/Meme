import unittest

from app.core.memory.validation.graph_validator import validate_graph


class MemoryGraphValidatorTests(unittest.TestCase):
    def test_detects_multiple_self_alias_entities_and_missing_evidence(self):
        report = validate_graph(
            user_id="user-1",
            entities=[
                {
                    "id": "self-1",
                    "name": "用户",
                    "type": "生命体",
                    "is_self": True,
                    "is_active": True,
                    "is_invalidated": False,
                },
                {
                    "id": "alias-1",
                    "name": "林夕",
                    "type": "称呼别名",
                    "is_active": True,
                    "is_invalidated": False,
                },
                {
                    "id": "self-2",
                    "name": "林夕",
                    "type": "生命体",
                    "is_self": True,
                    "is_active": True,
                    "is_invalidated": False,
                },
            ],
            relations=[
                {
                    "id": "rel-1",
                    "source_id": "self-1",
                    "target_id": "alias-1",
                    "statement_id": "missing-statement",
                    "statement_exists": False,
                    "source_text": "",
                }
            ],
        )

        rule_ids = {finding.rule_id for finding in report.findings}
        self.assertIn("SELF_MULTIPLE_ACTIVE", rule_ids)
        self.assertIn("ALIAS_ENTITY_PRESENT", rule_ids)
        self.assertIn("RELATION_EVIDENCE_MISSING", rule_ids)
        self.assertEqual(report.entity_count, 3)
        self.assertEqual(report.relation_count, 1)
        self.assertGreaterEqual(report.error_count, 1)

    def test_ignores_logically_inactive_duplicates_for_active_duplicate_rule(self):
        report = validate_graph(
            user_id="user-1",
            entities=[
                {"id": "a", "name": "Python", "type": "技能", "is_active": True},
                {"id": "b", "name": "Python", "type": "技能", "is_active": False},
            ],
            relations=[],
        )

        self.assertNotIn(
            "DUPLICATE_ACTIVE_ENTITY", {finding.rule_id for finding in report.findings}
        )
        self.assertIn("INACTIVE_ENTITY_PRESENT", {finding.rule_id for finding in report.findings})

    def test_post_migration_graph_has_one_active_self_and_keeps_inactive_alias_for_audit(self):
        report = validate_graph(
            user_id="user-1",
            entities=[
                {
                    "id": "self-1",
                    "name": "林舟",
                    "type": "生命体",
                    "identity_key": "self:user-1",
                    "is_self": True,
                    "is_active": True,
                    "is_invalidated": False,
                },
                {
                    "id": "ordinary-1",
                    "name": "多多",
                    "type": "生命体",
                    "is_active": True,
                    "is_invalidated": False,
                },
                {
                    "id": "alias-1",
                    "name": "林舟",
                    "type": "称呼别名",
                    "is_active": False,
                    "is_invalidated": False,
                    "merged_into": "self-1",
                },
            ],
            relations=[],
        )

        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(
            {finding.rule_id for finding in report.findings},
            {"INACTIVE_ENTITY_PRESENT"},
        )


if __name__ == "__main__":
    unittest.main()
