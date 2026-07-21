import unittest

from canonical_payload import canonical_json


class CanonicalJsonTests(unittest.TestCase):
    def test_primitives_and_integer_boundaries(self):
        self.assertEqual(canonical_json(None), b"null")
        self.assertEqual(canonical_json(True), b"true")
        self.assertEqual(canonical_json(False), b"false")
        self.assertEqual(canonical_json(-(2**63)), b"-9223372036854775808")
        self.assertEqual(canonical_json(2**63 - 1), b"9223372036854775807")

    def test_normalizes_nested_strings_and_sorts_keys(self):
        value = {"é": "e\u0301", "a": [True, None, -2]}
        self.assertEqual(canonical_json(value), '{"a":[true,null,-2],"é":"é"}'.encode())

    def test_sorts_keys_by_normalized_utf8(self):
        self.assertEqual(
            canonical_json({"Ω": 3, "é": 2, "z": 1}),
            '{"z":1,"é":2,"Ω":3}'.encode(),
        )

    def test_required_string_escapes(self):
        value = '"\b\t\n\f\r\x01\\'
        expected = ('"' + r'\"\b\t\n\f\r\u0001\\' + '"').encode("ascii")
        self.assertEqual(canonical_json(value), expected)

    def test_rejects_types_and_integer_range(self):
        for value in (1.0, (1, 2), object(), 2**63, -(2**63) - 1):
            expected = ValueError if type(value) is int else TypeError
            with self.subTest(value=repr(value)), self.assertRaises(expected):
                canonical_json(value)

    def test_rejects_surrogates(self):
        for value in ("\ud800", {"\udfff": 1}):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                canonical_json(value)

    def test_rejects_keys_and_normalization_collisions(self):
        with self.assertRaises(TypeError):
            canonical_json({1: "one"})
        with self.assertRaises(ValueError):
            canonical_json({"é": 1, "e\u0301": 2})

    def test_cycles_and_shared_values(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ValueError):
            canonical_json(cycle)
        shared = [1]
        self.assertEqual(canonical_json([shared, shared]), b"[[1],[1]]")


if __name__ == "__main__":
    unittest.main()
