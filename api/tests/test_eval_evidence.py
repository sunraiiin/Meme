import asyncio
import unittest

from eval.run_manifest import fixture_counts, fixtures_sha256
from eval.stats import bootstrap_mean_ci, latency_summary, percentile
from eval.tasks.identity import eval_identity


class EvalEvidenceTests(unittest.TestCase):
    def test_fixture_manifest_is_stable_and_counts_new_suites(self):
        digest = fixtures_sha256()
        counts = fixture_counts()

        self.assertEqual(len(digest), 64)
        self.assertEqual(counts["retrieval"], 22)
        self.assertEqual(counts["memory_retrieval"], 19)
        self.assertEqual(counts["rag_negative"], 8)
        self.assertEqual(counts["memory_retrieval_negative"], 8)
        self.assertEqual(counts["memory_identity"], 9)

    def test_latency_and_bootstrap_statistics_are_deterministic(self):
        self.assertEqual(percentile([1, 2, 3, 4], 0.95), 4)
        self.assertEqual(
            latency_summary([10.0, 20.0, 30.0]),
            {"AvgLatencyMs": 20.0, "P95LatencyMs": 30.0},
        )
        self.assertEqual(
            bootstrap_mean_ci([0.0, 1.0, 1.0], seed=7, samples=200),
            bootstrap_mean_ci([0.0, 1.0, 1.0], seed=7, samples=200),
        )

    def test_identity_safety_fixture_passes(self):
        table, details = asyncio.run(eval_identity())
        row = table["确定性身份安全层"]

        self.assertEqual(row["CaseAccuracy"], 1.0)
        self.assertEqual(row["UnsafeSelfLinkRate"], 0.0)
        self.assertEqual(row["StableSelfRate"], 1.0)
        self.assertEqual(len(details), 9)


if __name__ == "__main__":
    unittest.main()
