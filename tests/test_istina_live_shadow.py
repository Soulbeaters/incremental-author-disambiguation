import unittest

from experiments.istina_live_shadow import (
    hash_identifier,
    release_shadow_is_verified,
    select_known_shadow_mentions,
)


class IstinaLiveShadowTests(unittest.TestCase):
    def test_smoke_does_not_satisfy_release_volume(self):
        self.assertFalse(release_shadow_is_verified(True, 5, 500))
        self.assertFalse(release_shadow_is_verified(False, 500, 500))
        self.assertTrue(release_shadow_is_verified(True, 500, 500))
        self.assertFalse(release_shadow_is_verified(
            True,
            500,
            500,
            papers=99,
            minimum_papers=100,
        ))
        self.assertTrue(release_shadow_is_verified(
            True,
            500,
            500,
            papers=100,
            minimum_papers=100,
        ))

    def test_identifier_hash_is_keyed_and_does_not_expose_input(self):
        first = hash_identifier("private-article", "secret-one")
        second = hash_identifier("private-article", "secret-two")

        self.assertRegex(first, r"^[0-9a-f]{16}$")
        self.assertNotEqual(first, second)
        self.assertNotIn("private-article", first)

    def test_plan_sample_is_deterministic_and_covers_required_papers(self):
        mentions = [
            {
                "article_index": article,
                "position": position,
                "gold_author_id": "known",
            }
            for article, position in [(1, 1), (1, 2), (2, 1), (3, 1), (3, 2)]
        ]

        selected = select_known_shadow_mentions(
            mentions,
            {"known"},
            limit=4,
            minimum_papers=3,
        )

        self.assertEqual(
            [(item["article_index"], item["position"]) for item in selected],
            [(1, 1), (2, 1), (3, 1), (1, 2)],
        )


if __name__ == "__main__":
    unittest.main()
