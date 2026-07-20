import unittest

from experiments.istina_online_read_load import (
    INSTITUTIONAL_LOAD_SCOPE,
    USER_CANARY_SCOPE,
    assess_load_evidence,
    percentile,
    run_read_only_load,
    validate_load_approval_scope,
)


class IstinaOnlineReadLoadTests(unittest.TestCase):
    def test_read_only_load_counts_successes_and_errors(self):
        calls = []

        def request(article):
            calls.append(article["id"])
            if len(calls) == 3:
                raise TimeoutError("injected")

        result = run_read_only_load(
            [{"id": "p1", "authors": [{"id": "a1"}]}],
            request_count=5,
            concurrency=1,
            max_rps=0,
            request_func=request,
        )

        self.assertEqual(result["requests"], 5)
        self.assertEqual(result["completed"], 5)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["error_rate"], 0.2)
        self.assertEqual(calls, ["p1"] * 5)

    def test_articles_cycle_deterministically(self):
        calls = []
        run_read_only_load(
            [
                {"id": "p1", "authors": [{"id": "a1"}]},
                {"id": "p2", "authors": [{"id": "a2"}]},
            ],
            request_count=5,
            concurrency=1,
            max_rps=0,
            request_func=lambda article: calls.append(article["id"]),
        )

        self.assertEqual(calls, ["p1", "p2", "p1", "p2", "p1"])

    def test_invalid_concurrency_or_empty_dataset_is_rejected(self):
        with self.assertRaises(ValueError):
            run_read_only_load(
                [],
                request_count=1,
                concurrency=1,
                max_rps=0,
                request_func=lambda article: None,
            )
        with self.assertRaises(ValueError):
            run_read_only_load(
                [{"authors": [{}]}],
                request_count=1,
                concurrency=17,
                max_rps=0,
                request_func=lambda article: None,
            )

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([4.0, 1.0, 3.0, 2.0], 0.50), 2.0)
        self.assertEqual(percentile([4.0, 1.0, 3.0, 2.0], 0.95), 4.0)

    def test_user_canary_can_never_be_release_verified(self):
        load = {
            "requests": 1000,
            "error_rate": 0.0,
            "latency_ms_p95": 100.0,
        }

        result = assess_load_evidence(
            load,
            approval_scope=USER_CANARY_SCOPE,
        )

        self.assertTrue(result["threshold_passed"])
        self.assertFalse(result["institutional_approval"])
        self.assertFalse(result["verified"])
        self.assertEqual(
            result["evidence_classification"],
            "bounded_non_release_canary",
        )

    def test_approved_institutional_load_can_verify_thresholds(self):
        load = {
            "requests": 1000,
            "error_rate": 0.0,
            "latency_ms_p95": 100.0,
        }

        result = assess_load_evidence(
            load,
            approval_scope=INSTITUTIONAL_LOAD_SCOPE,
        )

        self.assertTrue(result["verified"])
        self.assertEqual(
            result["evidence_classification"],
            "release_scale_online_load",
        )

    def test_missing_or_nonfinite_metrics_fail_closed(self):
        for load in (
            {"requests": 1000, "latency_ms_p95": 100.0},
            {
                "requests": 1000,
                "error_rate": float("nan"),
                "latency_ms_p95": 100.0,
            },
            {
                "requests": 1000,
                "error_rate": 0.0,
                "latency_ms_p95": float("inf"),
            },
        ):
            result = assess_load_evidence(
                load,
                approval_scope=INSTITUTIONAL_LOAD_SCOPE,
            )
            self.assertFalse(result["verified"])
            self.assertFalse(result["threshold_passed"])

    def test_user_canary_request_cap_is_enforced(self):
        validate_load_approval_scope(20, USER_CANARY_SCOPE)
        with self.assertRaisesRegex(ValueError, "capped at 20"):
            validate_load_approval_scope(21, USER_CANARY_SCOPE)


if __name__ == "__main__":
    unittest.main()
