import math
import unittest

from structured_redaction import DEFAULT_SENSITIVE_KEYS, RedactionError, redact_record


class ExplodesIfCopied:
    def __deepcopy__(self, memo):
        raise AssertionError("must not inspect a sensitive value")


class RedactionTests(unittest.TestCase):
    def test_defaults_normalization_nested_shapes_and_no_mutation(self):
        record = {"User": {"API_KEY": "abc", "profile": ("ok", {"Access-Token": "xyz"})}, "PASSWORD": "p", "message": "token=visible"}
        got = redact_record(record)
        self.assertEqual(got, {"User": {"API_KEY": "[REDACTED]", "profile": ("ok", {"Access-Token": "[REDACTED]"})}, "PASSWORD": "[REDACTED]", "message": "token=visible"})
        self.assertEqual(record["User"]["API_KEY"], "abc")
        self.assertIsInstance(got["User"]["profile"], tuple)
        self.assertIn("set-cookie", DEFAULT_SENSITIVE_KEYS)

    def test_sensitive_value_is_not_inspected_or_copied(self):
        cyclic = []
        cyclic.append(cyclic)
        record = {"authorization": ExplodesIfCopied(), "token": cyclic, "safe": 1}
        self.assertEqual(redact_record(record), {"authorization": "[REDACTED]", "token": "[REDACTED]", "safe": 1})

    def test_custom_keys_replacement_and_shared_containers(self):
        shared = [{"pin-code": "1234", "visible": True}]
        record = {"left": shared, "right": shared}
        got = redact_record(record, sensitive_keys=(key for key in ["PIN_CODE"]), replacement="***")
        self.assertEqual(got["left"], [{"pin-code": "***", "visible": True}])
        self.assertEqual(got["right"], got["left"])
        self.assertIsNot(got["left"], got["right"])
        self.assertIsNot(got["left"][0], got["right"][0])

    def test_cycle_reports_escaped_path(self):
        child = {}
        root = {"a/b~c": child}
        child["again"] = root
        with self.assertRaises(RedactionError) as caught:
            redact_record(root)
        self.assertEqual(caught.exception.path, "/a~1b~0c/again")
        self.assertIn("cycle", caught.exception.reason.lower())

    def test_depth_boundary_counts_only_containers(self):
        record = {"scalar": "ok", "nested": {"value": 1}}
        self.assertEqual(redact_record(record, max_depth=1), record)
        with self.assertRaises(RedactionError) as caught:
            redact_record({"a": {"b": []}}, max_depth=1)
        self.assertEqual(caught.exception.path, "/a/b")

    def test_unsupported_values_keys_and_nonfinite_numbers(self):
        cases = [({"safe": object()}, "/safe"), ({1: "value"}, ""), ({"x": math.inf}, "/x")]
        for record, path in cases:
            with self.subTest(record=record):
                with self.assertRaises(RedactionError) as caught:
                    redact_record(record)
                self.assertEqual(caught.exception.path, path)

    def test_argument_validation_and_tuple_root(self):
        self.assertEqual(redact_record(({"passwd": "x"}, 2)), ({"passwd": "[REDACTED]"}, 2))
        calls = [
            lambda: redact_record({}, sensitive_keys="token"),
            lambda: redact_record({}, sensitive_keys=[""]),
            lambda: redact_record({}, sensitive_keys=[1]),
            lambda: redact_record({}, replacement=None),
            lambda: redact_record({}, max_depth=True),
            lambda: redact_record({}, max_depth=-1),
        ]
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises((TypeError, ValueError)):
                    call()


if __name__ == "__main__":
    unittest.main()
