import math
import unittest

from secret_redactor import redact_secrets


class SecretRedactorTests(unittest.TestCase):
    def test_nested_redaction_and_key_normalization(self):
        source = {"User": "sam", "Api-Key": "one", "nested": [{"PASS_WORD": "two"},
                  {"ToKeN": {"deep": "must not leak"}}]}
        result = redact_secrets(source)
        self.assertEqual(result, {"User": "sam", "Api-Key": "[REDACTED]",
                                  "nested": [{"PASS_WORD": "[REDACTED]"},
                                             {"ToKeN": "[REDACTED]"}]})

    def test_source_is_not_mutated_and_result_is_detached(self):
        source = {"items": [{"name": "a"}], "token": "visible-in-source"}
        result = redact_secrets(source)
        self.assertEqual(source, {"items": [{"name": "a"}], "token": "visible-in-source"})
        result["items"][0]["name"] = "changed"
        self.assertEqual(source["items"][0]["name"], "a")
        self.assertIsNot(result, source)

    def test_lists_tuples_and_shared_aliases_are_preserved(self):
        shared = [{"ok": 1}]
        source = {"left": shared, "right": shared, "tuple": ("x", {"secret": "s"})}
        result = redact_secrets(source)
        self.assertIs(result["left"], result["right"])
        self.assertIsNot(result["left"], shared)
        self.assertIsInstance(result["tuple"], tuple)
        self.assertEqual(result["tuple"], ("x", {"secret": "[REDACTED]"}))

    def test_custom_keys_and_replacement(self):
        result = redact_secrets({"session-id": "x", "token": "kept"},
                                sensitive_keys=["SESSION_ID"], replacement="***")
        self.assertEqual(result, {"session-id": "***", "token": "kept"})

    def test_cycles_are_rejected_without_mutation(self):
        source = {"name": "cycle"}
        source["self"] = source
        with self.assertRaises(ValueError):
            redact_secrets(source)
        self.assertIs(source["self"], source)
        self.assertEqual(source["name"], "cycle")

    def test_complete_input_is_validated_even_under_sensitive_key(self):
        with self.assertRaises(TypeError):
            redact_secrets({"token": object()})
        with self.assertRaises(ValueError):
            redact_secrets({"password": math.nan})

    def test_non_json_values_and_keys_are_rejected(self):
        bad = [{1: "value"}, {"value": {1, 2}}, {"value": b"bytes"}, {"value": math.inf}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                redact_secrets(value)

    def test_sensitive_key_configuration_is_strict(self):
        bad = ["token", [""], ["-_"], [3]]
        for sensitive_keys in bad:
            with self.subTest(sensitive_keys=sensitive_keys), self.assertRaises((TypeError, ValueError)):
                redact_secrets({}, sensitive_keys=sensitive_keys)
        with self.assertRaises(TypeError):
            redact_secrets({}, replacement=None)

    def test_primitive_types_remain_exact(self):
        source = [None, True, False, 3, 2.5, "text"]
        result = redact_secrets(source)
        self.assertEqual(result, source)
        for actual, expected in zip(result, source):
            self.assertIs(type(actual), type(expected))


unittest.main()
