import unittest

from semver_range import Range, Version, satisfies


class SemanticVersionTests(unittest.TestCase):
    def test_parse_fields_build_equality_and_hash(self):
        value = Version.parse("1.2.3-alpha.1+build.7")
        self.assertEqual((value.major, value.minor, value.patch), (1, 2, 3))
        self.assertEqual(value.prerelease, ("alpha", "1"))
        self.assertEqual(value.build, ("build", "7"))
        self.assertEqual(Version.parse("1.2.3+x"), Version.parse("1.2.3+y"))
        self.assertEqual(hash(Version.parse("1.2.3+x")), hash(Version.parse("1.2.3+y")))
        with self.assertRaises(AttributeError):
            value.major = 9
        parsed_range = Range.parse("1.x")
        with self.assertRaises(AttributeError):
            parsed_range._arms = ()

    def test_semver_prerelease_order(self):
        texts = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        versions = [Version.parse(text) for text in texts]
        self.assertEqual(sorted(reversed(versions)), versions)
        self.assertTrue(Version.parse("1.0.0-1") < Version.parse("1.0.0-alpha"))

    def test_strict_version_validation(self):
        for text in ("1.2", "01.2.3", "1.02.3", "1.2.03", "1.2.3-", "1.2.3-a..b", "1.2.3-01", "v1.2.3", "1.2.3+bad_thing"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    Version.parse(text)
        with self.assertRaises(TypeError):
            Version.parse(123)

    def test_comparators_and_and_or(self):
        expression = ">=1.2.0 <2.0.0 || =3.0.0"
        self.assertTrue(satisfies("1.9.9", expression))
        self.assertFalse(satisfies("2.0.0", expression))
        self.assertTrue(satisfies(Version.parse("3.0.0+meta"), expression))
        self.assertFalse(satisfies("3.0.1", expression))

    def test_wildcard_tilde_and_caret_boundaries(self):
        cases = [
            ("1.9.0", "1.x", True), ("2.0.0", "1.x", False),
            ("1.2.99", "1.2.X", True), ("1.3.0", "1.2.x", False),
            ("1.3.0", "~1.2.3", False), ("1.2.3", "~1.2.3", True),
            ("1.9.0", "^1.2.3", True), ("2.0.0", "^1.2.3", False),
            ("0.2.9", "^0.2.3", True), ("0.3.0", "^0.2.3", False),
            ("0.0.4", "^0.0.3", False), ("9.0.0", "*", True),
        ]
        for version, expression, expected in cases:
            with self.subTest(version=version, expression=expression):
                self.assertEqual(satisfies(version, expression), expected)

    def test_prerelease_gate_is_per_arm(self):
        self.assertFalse(satisfies("1.3.0-alpha", ">=1.0.0 <2.0.0"))
        self.assertTrue(satisfies("1.3.0-alpha.2", ">=1.3.0-alpha <1.3.0"))
        self.assertFalse(satisfies("1.4.0-alpha", ">=1.3.0-alpha <2.0.0"))
        self.assertTrue(satisfies("2.0.0-beta", "1.x || >=2.0.0-beta <2.0.0"))
        self.assertFalse(satisfies("2.0.0-beta", "*"))

    def test_range_validation_and_contains_types(self):
        for expression in ("", " ", "|| 1.2.3", "1.2.3 ||", "1.2", "!=1.2.3", "^1.2", "1.*.3", ">"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    Range.parse(expression)
        with self.assertRaises(TypeError):
            Range.parse(None)
        with self.assertRaises(TypeError):
            Range.parse("*").contains(123)


if __name__ == "__main__":
    unittest.main()
