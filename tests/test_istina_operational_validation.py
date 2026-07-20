import math
import unittest

from experiments.istina_operational_validation import (
    OFFLINE_LOAD_P95_LIMIT_MS,
    OFFLINE_LOAD_VERIFICATION_METHOD,
    summarize_load_measurements,
)


class IstinaOperationalValidationTests(unittest.TestCase):
    def test_summary_keeps_overall_threshold_and_iteration_distribution(self):
        result = summarize_load_measurements(
            [[1.0, 2.0], [49.0, 51.0]],
            operations=4,
            elapsed_seconds=2.0,
            deterministic_hash_mismatches=0,
        )

        self.assertFalse(result["verified"])
        self.assertEqual(
            result["verification_method"],
            OFFLINE_LOAD_VERIFICATION_METHOD,
        )
        self.assertEqual(
            result["acceptance_threshold_ms_p95"],
            OFFLINE_LOAD_P95_LIMIT_MS,
        )
        self.assertEqual(result["latency_ms_p95"], 51.0)
        self.assertEqual(result["threshold_margin_ms"], -1.0)
        self.assertEqual(result["iteration_latency_ms_p95"], [2.0, 51.0])
        self.assertEqual(
            result["iteration_p95_summary_ms"],
            {
                "minimum": 2.0,
                "median": 2.0,
                "maximum": 51.0,
                "passing_iterations": 1,
                "total_iterations": 2,
            },
        )
        self.assertEqual(result["throughput_mentions_per_second"], 2.0)

    def test_hash_mismatch_fails_even_when_latency_passes(self):
        result = summarize_load_measurements(
            [[1.0, 2.0]],
            operations=2,
            elapsed_seconds=1.0,
            deterministic_hash_mismatches=1,
        )

        self.assertFalse(result["verified"])
        self.assertEqual(result["latency_ms_p95"], 2.0)

    def test_invalid_latency_or_operation_count_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "finite non-negative"):
            summarize_load_measurements(
                [[1.0, math.inf]],
                operations=2,
                elapsed_seconds=1.0,
                deterministic_hash_mismatches=0,
            )
        with self.assertRaisesRegex(ValueError, "operation count"):
            summarize_load_measurements(
                [[1.0]],
                operations=2,
                elapsed_seconds=1.0,
                deterministic_hash_mismatches=0,
            )


if __name__ == "__main__":
    unittest.main()
