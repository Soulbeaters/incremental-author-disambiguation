import unittest

from experiments.istina_live_shadow import hash_identifier, release_shadow_is_verified


class IstinaLiveShadowTests(unittest.TestCase):
    def test_smoke_does_not_satisfy_release_volume(self):
        self.assertFalse(release_shadow_is_verified(True, 5, 500))
        self.assertFalse(release_shadow_is_verified(False, 500, 500))
        self.assertTrue(release_shadow_is_verified(True, 500, 500))

    def test_identifier_hash_is_keyed_and_does_not_expose_input(self):
        first = hash_identifier("private-article", "secret-one")
        second = hash_identifier("private-article", "secret-two")

        self.assertRegex(first, r"^[0-9a-f]{16}$")
        self.assertNotEqual(first, second)
        self.assertNotIn("private-article", first)


if __name__ == "__main__":
    unittest.main()
