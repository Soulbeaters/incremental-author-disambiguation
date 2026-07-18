import unittest

from disambiguation_engine.surname_risk import is_high_risk_surname


class SurnameRiskTests(unittest.TestCase):
    def test_common_east_asian_romanizations_are_high_risk(self):
        for surname in ("Qian", "Zhang", "Tanaka", "Kim"):
            with self.subTest(surname=surname):
                self.assertTrue(is_high_risk_surname(surname))

    def test_cjk_scripts_are_high_risk(self):
        for surname in ("张", "佐藤", "김"):
            with self.subTest(surname=surname):
                self.assertTrue(is_high_risk_surname(surname))

    def test_non_east_asian_surname_is_not_flagged(self):
        self.assertFalse(is_high_risk_surname("Almira"))

    def test_common_western_surnames_are_high_risk(self):
        for surname in ("Rossi", "Müller", "Clark"):
            with self.subTest(surname=surname):
                self.assertTrue(is_high_risk_surname(surname))

    def test_official_high_frequency_south_asian_surnames_are_high_risk(self):
        for surname in ("Khan", "Ali", "Ahmed", "Hussain", "Singh"):
            with self.subTest(surname=surname):
                self.assertTrue(is_high_risk_surname(surname))


if __name__ == "__main__":
    unittest.main()
