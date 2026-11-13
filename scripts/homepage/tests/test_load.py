import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import CatalogError, loads_yaml


class LoadTests(unittest.TestCase):
    def test_rule01_duplicate_key(self):
        with self.assertRaisesRegex(CatalogError, "'a'"):
            loads_yaml("a: 1\na: 2\n", "x")

    def test_merge_keys_allowed(self):
        self.assertEqual(loads_yaml("b: &b {x: 1}\nc:\n  <<: *b\n  y: 2\n", "x")["c"], {"x": 1, "y": 2})

    def test_rule02_unquoted_truthy(self):
        for bad in ("yes", "No", "on", "OFF"):
            with self.subTest(bad), self.assertRaises(CatalogError):
                loads_yaml(f"k: {bad}\n", "x")
        for good, want in (('"yes"', "yes"), ("true", True), ("false", False), ("yesterday", "yesterday")):
            with self.subTest(good):
                self.assertEqual(loads_yaml(f"k: {good}\n", "x"), {"k": want})

    def test_prettier_form_equal(self):
        single = "a: 'x'\nl:\n  - 'p'\n  - q: 'r'\n"
        double = 'a: "x"\nl:\n    - "p"\n    - q: "r"\n'
        self.assertEqual(loads_yaml(single, "x"), loads_yaml(double, "x"))


if __name__ == "__main__":
    unittest.main()
