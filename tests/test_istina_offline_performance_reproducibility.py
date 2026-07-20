import copy
import unittest

from evaluation.istina_offline_performance_reproducibility import (
    METHOD,
    build_performance_reproducibility,
)
from experiments.istina_operational_validation import (
    OFFLINE_LOAD_P95_LIMIT_MS,
    OFFLINE_LOAD_VERIFICATION_METHOD,
)


DATASET_SHA = "b" * 64
CODE_REVISION = "a" * 40


def trial(trial_id, p95):
    iteration_p95 = [p95 - 1.0, p95]
    verified = p95 <= OFFLINE_LOAD_P95_LIMIT_MS
    return {
        "schema_version": 1,
        "protocol": {
            "dataset_sha256": DATASET_SHA,
            "code_revision": CODE_REVISION,
            "performance_trial_id": trial_id,
            "split_strategy": "temporal",
            "train_through_year": 2023,
            "test_mentions": 2,
            "load_iterations": 2,
        },
        "operational_validation": {
            "offline_load_test": {
                "verified": verified,
                "verification_method": OFFLINE_LOAD_VERIFICATION_METHOD,
                "acceptance_threshold_ms_p95": OFFLINE_LOAD_P95_LIMIT_MS,
                "threshold_margin_ms": OFFLINE_LOAD_P95_LIMIT_MS - p95,
                "load_operations": 4,
                "throughput_mentions_per_second": 2.0,
                "latency_ms_p95": p95,
                "iteration_latency_ms_p95": iteration_p95,
                "iteration_p95_summary_ms": {
                    "minimum": p95 - 1.0,
                    "median": p95 - 1.0,
                    "maximum": p95,
                    "passing_iterations": sum(
                        value <= OFFLINE_LOAD_P95_LIMIT_MS
                        for value in iteration_p95
                    ),
                    "total_iterations": 2,
                },
                "deterministic_hash_mismatches": 0,
                "environment": {
                    "python_version": "3.11.9",
                    "operating_system": "Windows",
                    "host_identifier_included": False,
                },
            }
        },
    }


class IstinaOfflinePerformanceReproducibilityTests(unittest.TestCase):
    def build(self, trials):
        return build_performance_reproducibility(
            trials=trials,
            trial_sha256s=[str(index) * 64 for index in range(1, len(trials) + 1)],
            expected_dataset_sha256=DATASET_SHA,
            expected_code_revision=CODE_REVISION,
            generated_at="2026-07-20T00:00:00+00:00",
        )

    def test_three_passing_trials_produce_verified_path_free_summary(self):
        result = self.build([
            trial("trial-1", 45.0),
            trial("trial-2", 46.0),
            trial("trial-3", 47.0),
        ])

        self.assertEqual(result["method"], METHOD)
        self.assertTrue(result["summary"]["verified"])
        self.assertEqual(result["summary"]["passing_trials"], 3)
        self.assertEqual(result["summary"]["combined_replay_operations"], 12)
        self.assertEqual(result["metrics"]["trial_p95_median_ms"], 46.0)
        self.assertEqual(result["metrics"]["trial_p95_maximum_ms"], 47.0)
        self.assertFalse(result["protocol"]["host_identifier_included"])
        self.assertNotIn("path", str(result).lower())

    def test_one_failed_trial_keeps_aggregate_failed(self):
        result = self.build([
            trial("trial-1", 45.0),
            trial("trial-2", 51.0),
            trial("trial-3", 47.0),
        ])

        self.assertFalse(result["summary"]["verified"])
        self.assertEqual(result["summary"]["passing_trials"], 2)
        self.assertEqual(result["summary"]["failed_trials"], 1)

    def test_duplicate_or_tampered_trials_fail_closed(self):
        documents = [
            trial("trial-1", 45.0),
            trial("trial-2", 46.0),
            trial("trial-3", 47.0),
        ]
        duplicate_id = copy.deepcopy(documents)
        duplicate_id[1]["protocol"]["performance_trial_id"] = "trial-1"
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            self.build(duplicate_id)

        tampered = copy.deepcopy(documents)
        tampered[0]["operational_validation"]["offline_load_test"][
            "threshold_margin_ms"
        ] = 999.0
        with self.assertRaisesRegex(ValueError, "margin"):
            self.build(tampered)


if __name__ == "__main__":
    unittest.main()
