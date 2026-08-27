import asyncio
import tempfile
import unittest
from pathlib import Path

from eval.benchmarks.hotpotqa.runner import (
    _embedding_chunks,
    _load_checkpoint,
    _write_checkpoint,
)
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

    def test_hotpot_long_sentence_is_split_before_embedding(self):
        chunks = _embedding_chunks("x" * 4500)

        self.assertEqual([len(chunk) for chunk in chunks], [2000, 2000, 500])

    def test_hotpot_checkpoint_is_atomic_and_retries_error_rows(self):
        signature = {"sample": 2, "seed": 42}
        details = [
            {"qid": "ok", "em": 1.0},
            {"qid": "retry", "em": 0.0, "error": {"type": "Timeout"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.json"
            _write_checkpoint(path, signature, details)

            restored = _load_checkpoint(path, signature)

        self.assertEqual([row["qid"] for row in restored], ["ok"])


if __name__ == "__main__":
    unittest.main()
