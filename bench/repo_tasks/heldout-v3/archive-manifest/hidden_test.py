from dataclasses import FrozenInstanceError
import unittest

from archive_manifest import ArchiveEntry, ManifestError, validate_manifest


HASH_A = "a" * 64
HASH_B = "0123456789abcdef" * 4


def file_entry(path="a.txt", size=1, digest=HASH_A):
    return {"path": path, "type": "file", "size": size, "sha256": digest}


def dir_entry(path="assets"):
    return {"path": path, "type": "dir", "size": 0, "sha256": None}


class ArchiveManifestTests(unittest.TestCase):
    def test_valid_manifest_returns_frozen_detached_entries(self):
        source = [dir_entry(), file_entry("assets/a.txt", 3, HASH_B)]
        result = validate_manifest(source, max_files=2, max_total_size=3)
        self.assertEqual(result, (ArchiveEntry("assets", "dir", 0, None),
                                  ArchiveEntry("assets/a.txt", "file", 3, HASH_B)))
        source[1]["path"] = "changed"
        self.assertEqual(result[1].path, "assets/a.txt")
        with self.assertRaises(FrozenInstanceError):
            result[0].path = "other"

    def test_canonical_relative_paths_only(self):
        bad = ["", "/abs", "a\\b", "a\x00b", "a//b", "./a", "a/./b", "../a", "a/../b"]
        for path in bad:
            with self.subTest(path=path), self.assertRaises(ManifestError):
                validate_manifest([file_entry(path)], max_files=1, max_total_size=1)

    def test_similar_dot_names_and_unicode_are_valid(self):
        paths = ["a..b", ".hidden", "café/menu.txt"]
        result = validate_manifest([file_entry(path, 0) for path in paths],
                                   max_files=3, max_total_size=0)
        self.assertEqual([entry.path for entry in result], paths)

    def test_duplicates_and_file_ancestor_conflicts_are_rejected(self):
        cases = [
            [file_entry("a"), file_entry("a")],
            [file_entry("a"), file_entry("a/b")],
            [file_entry("a/b"), file_entry("a")],
            [dir_entry("a/b"), file_entry("a")],
        ]
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(ManifestError):
                validate_manifest(entries, max_files=3, max_total_size=10)

    def test_entry_schema_and_types_are_strict(self):
        bad = [
            {"path": "a", "type": "file", "size": 1},
            dict(file_entry(), extra=True),
            {"path": 3, "type": "file", "size": 1, "sha256": HASH_A},
            {"path": "a", "type": "symlink", "size": 0, "sha256": None},
            ["not", "a", "mapping"],
        ]
        for entry in bad:
            with self.subTest(entry=entry), self.assertRaises((TypeError, ManifestError)):
                validate_manifest([entry], max_files=1, max_total_size=1)

    def test_file_metadata_is_strict(self):
        bad = [
            file_entry(size=True), file_entry(size=-1), file_entry(size=1.0),
            file_entry(digest="A" * 64), file_entry(digest="a" * 63),
            file_entry(digest="g" * 64),
        ]
        for entry in bad:
            with self.subTest(entry=entry), self.assertRaises(ManifestError):
                validate_manifest([entry], max_files=1, max_total_size=10)

    def test_directory_metadata_is_exact(self):
        for entry in (
            {"path": "d", "type": "dir", "size": False, "sha256": None},
            {"path": "d", "type": "dir", "size": 1, "sha256": None},
            {"path": "d", "type": "dir", "size": 0, "sha256": HASH_A},
        ):
            with self.subTest(entry=entry), self.assertRaises(ManifestError):
                validate_manifest([entry], max_files=1, max_total_size=1)

    def test_limits_are_exact_and_invalid_limits_are_rejected(self):
        self.assertEqual(len(validate_manifest([file_entry(size=2)], max_files=1,
                                              max_total_size=2)), 1)
        with self.assertRaises(ManifestError):
            validate_manifest([file_entry(size=3)], max_files=1, max_total_size=2)
        for kwargs in ({"max_files": True, "max_total_size": 1},
                       {"max_files": -1, "max_total_size": 1},
                       {"max_files": 1, "max_total_size": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                validate_manifest([], **kwargs)

    def test_entry_limit_stops_consumption(self):
        consumed = []
        def source():
            for index in range(4):
                consumed.append(index)
                if index == 3:
                    raise AssertionError("iterated past the required limit check")
                yield file_entry(f"{index}.txt", 0)
        with self.assertRaises(ManifestError):
            validate_manifest(source(), max_files=2, max_total_size=0)
        self.assertEqual(consumed, [0, 1, 2])


unittest.main()
