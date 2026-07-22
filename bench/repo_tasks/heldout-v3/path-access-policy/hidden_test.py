import os
from pathlib import Path
import tempfile
import unittest

from path_policy import PathAccessError, resolve_allowed_path


class PathPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "allowed"
        self.root.mkdir()
        (self.root / "dir").mkdir()
        (self.root / "dir" / "item.txt").write_text("item", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_and_missing_descendants_resolve(self):
        self.assertEqual(resolve_allowed_path(self.root, "dir/item.txt"),
                         (self.root / "dir" / "item.txt").resolve())
        result = resolve_allowed_path(os.fspath(self.root), "dir/new.txt")
        self.assertEqual(result, (self.root / "dir" / "new.txt").resolve())
        self.assertFalse(result.exists())

    def test_root_itself_can_be_addressed_by_a_real_child_symlink(self):
        (self.root / "back").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(resolve_allowed_path(self.root, "back"), self.root.resolve())

    def test_parent_traversal_and_absolute_paths_are_rejected(self):
        for requested in ("../outside", "dir/../item", str(self.base / "outside")):
            with self.subTest(requested=requested), self.assertRaises(PathAccessError):
                resolve_allowed_path(self.root, requested)

    def test_noncanonical_or_platform_ambiguous_paths_are_rejected(self):
        for requested in ("", ".", "dir//item", "dir/./item", "dir\\item", "dir/\x00item"):
            with self.subTest(requested=requested), self.assertRaises(PathAccessError):
                resolve_allowed_path(self.root, requested)

    def test_symlink_to_outside_is_rejected_for_existing_and_missing_targets(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "data").write_text("secret", encoding="utf-8")
        (self.root / "escape").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(PathAccessError):
            resolve_allowed_path(self.root, "escape/data")
        with self.assertRaises(PathAccessError):
            resolve_allowed_path(self.root, "escape/not-created")

    def test_string_prefix_sibling_is_not_inside_root(self):
        sibling = self.base / "allowed-extra"
        sibling.mkdir()
        (self.root / "to-sibling").symlink_to(sibling, target_is_directory=True)
        with self.assertRaises(PathAccessError):
            resolve_allowed_path(self.root, "to-sibling/file")

    def test_root_must_exist_and_be_a_directory(self):
        file_root = self.base / "file-root"
        file_root.write_text("x", encoding="utf-8")
        with self.assertRaises(PathAccessError):
            resolve_allowed_path(self.base / "missing", "child")
        with self.assertRaises(PathAccessError):
            resolve_allowed_path(file_root, "child")

    def test_wrong_argument_types_and_no_side_effects(self):
        before = sorted(path.relative_to(self.base) for path in self.base.rglob("*"))
        with self.assertRaises(TypeError):
            resolve_allowed_path(self.root, b"dir/item.txt")
        with self.assertRaises(TypeError):
            resolve_allowed_path(42, "dir/item.txt")
        after = sorted(path.relative_to(self.base) for path in self.base.rglob("*"))
        self.assertEqual(after, before)


unittest.main()
