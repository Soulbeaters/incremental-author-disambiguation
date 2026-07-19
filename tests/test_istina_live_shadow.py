import unittest

from experiments.istina_live_shadow import release_shadow_is_verified


class IstinaLiveShadowTests(unittest.TestCase):
    def test_smoke_does_not_satisfy_release_volume(self):
        self.assertFalse(release_shadow_is_verified(True, 5, 500))
        self.assertFalse(release_shadow_is_verified(False, 500, 500))
        self.assertTrue(release_shadow_is_verified(True, 500, 500))


if __name__ == "__main__":
    unittest.main()
