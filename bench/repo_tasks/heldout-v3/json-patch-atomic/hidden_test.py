import copy
import math
import unittest

from json_patch import PatchError, apply_patch


class JsonPatchTests(unittest.TestCase):
    def test_add_replace_remove_and_pointer_escapes(self):
        original = {"a/b": {"~key": [1, 3]}, "keep": True}
        operations = [
            {"op": "add", "path": "/a~1b/~0key/1", "value": 2},
            {"op": "add", "path": "/a~1b/~0key/-", "value": 4},
            {"op": "replace", "path": "/keep", "value": False},
            {"op": "remove", "path": "/a~1b/~0key/0"},
        ]
        self.assertEqual(apply_patch(original, operations), {"a/b": {"~key": [2, 3, 4]}, "keep": False})
        self.assertEqual(original, {"a/b": {"~key": [1, 3]}, "keep": True})

    def test_root_operations_and_copy_is_deep(self):
        value = {"nested": [1]}
        copied = apply_patch(value, [{"op": "copy", "from": "", "path": "/clone"}])
        self.assertEqual(copied, {"nested": [1], "clone": {"nested": [1]}})
        self.assertIsNot(copied["clone"], copied)
        self.assertIsNot(copied["clone"]["nested"], copied["nested"])
        self.assertEqual(apply_patch(value, [{"op": "replace", "path": "", "value": [3]}]), [3])
        self.assertIsNone(apply_patch(value, [{"op": "remove", "path": ""}]))

    def test_move_array_post_removal_index_and_same_path(self):
        original = {"items": ["a", "b", "c", "d"]}
        moved = apply_patch(original, [{"op": "move", "from": "/items/1", "path": "/items/3"}])
        self.assertEqual(moved, {"items": ["a", "c", "d", "b"]})
        self.assertEqual(apply_patch(original, [{"op": "move", "from": "/items/1", "path": "/items/1"}]), original)

    def test_test_uses_json_type_sensitive_equality(self):
        document = {"one": 1, "truth": True, "nested": [{"x": 1.0}]}
        self.assertEqual(apply_patch(document, [{"op": "test", "path": "/nested", "value": [{"x": 1}]}]), document)
        with self.assertRaises(PatchError) as caught:
            apply_patch(document, [{"op": "test", "path": "/one", "value": True}])
        self.assertEqual(caught.exception.index, 0)
        self.assertEqual(caught.exception.operation, "test")

    def test_atomic_failure_preserves_document_and_operation_value(self):
        document = {"a": [1], "x": 2}
        inserted = {"deep": []}
        operations = [{"op": "add", "path": "/a/-", "value": inserted}, {"op": "remove", "path": "/missing"}]
        before_ops = copy.deepcopy(operations)
        with self.assertRaises(PatchError) as caught:
            apply_patch(document, operations)
        self.assertEqual(caught.exception.index, 1)
        self.assertEqual(document, {"a": [1], "x": 2})
        self.assertEqual(operations, before_ops)
        self.assertEqual(inserted, {"deep": []})

    def test_invalid_pointer_indices_and_descendant_move(self):
        document = {"a": {"b": 1}, "items": [1, 2]}
        bad_operations = [
            {"op": "remove", "path": "a"},
            {"op": "remove", "path": "/a/~2"},
            {"op": "remove", "path": "/items/01"},
            {"op": "remove", "path": "/items/-"},
            {"op": "add", "path": "/items/4", "value": 3},
            {"op": "move", "from": "/a", "path": "/a/c"},
        ]
        for operation in bad_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(PatchError):
                    apply_patch(document, [operation])

    def test_operation_validation_and_error_metadata(self):
        bad_operations = [
            {}, {"op": "unknown", "path": ""}, {"op": "add", "path": "/x"},
            {"op": "copy", "path": "/x"}, {"op": 1, "path": ""}, {"op": "test", "path": 1, "value": 2},
        ]
        for operation in bad_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(PatchError) as caught:
                    apply_patch({}, [operation])
                self.assertEqual(caught.exception.index, 0)
        with self.assertRaises(TypeError):
            apply_patch({}, "not operations")

    def test_json_compatibility_and_cycle_rejection(self):
        with self.assertRaises(TypeError):
            apply_patch({"x": (1, 2)}, [])
        with self.assertRaises(TypeError):
            apply_patch({}, [{"op": "add", "path": "/x", "value": math.inf}])
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(TypeError):
            apply_patch(cyclic, [])


if __name__ == "__main__":
    unittest.main()
