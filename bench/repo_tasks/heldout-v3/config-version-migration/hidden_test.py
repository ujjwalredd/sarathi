import copy
import unittest

from config_migration import ConfigError, migrate_config


EXPECTED = {
    "version": 3,
    "service": {"url": "https://api.example.test/v1?region=us", "timeout_ms": 5000},
    "auth": {"scheme": "bearer", "token": "test-token"},
    "retry": {"max_attempts": 3},
}


class ConfigMigrationTests(unittest.TestCase):
    def test_version_one_conversion_is_exact(self):
        source = {"version": 1, "endpoint": "https://api.example.test/v1?region=us",
                  "timeout_seconds": 5, "api_key": "test-token"}
        self.assertEqual(migrate_config(source), EXPECTED)

    def test_version_two_retry_count_becomes_attempt_count(self):
        source = {"version": 2,
                  "service": {"url": "https://api.example.test/v1?region=us", "timeout_ms": 5000},
                  "token": "test-token", "max_retries": 2}
        self.assertEqual(migrate_config(source), EXPECTED)

    def test_version_three_is_validated_and_deep_copied(self):
        source = copy.deepcopy(EXPECTED)
        result = migrate_config(source)
        self.assertEqual(result, EXPECTED)
        self.assertIsNot(result, source)
        self.assertIsNot(result["service"], source["service"])
        self.assertIsNot(result["auth"], source["auth"])
        result["service"]["timeout_ms"] = 10
        self.assertEqual(source["service"]["timeout_ms"], 5000)

    def test_exact_schemas_reject_missing_and_unknown_fields(self):
        cases = [
            {"version": 1, "endpoint": "https://x.test", "timeout_seconds": 1},
            {"version": 1, "endpoint": "https://x.test", "timeout_seconds": 1,
             "api_key": "x", "extra": True},
            {"version": 2, "service": {"url": "https://x.test", "timeout_ms": 1,
                                         "extra": 1}, "token": "x", "max_retries": 0},
            dict(EXPECTED, extra=1),
        ]
        for config in cases:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                migrate_config(config)

    def test_urls_must_be_safe_absolute_https_urls(self):
        bad_urls = ["http://x.test", "https:///missing-host", "https://user@x.test",
                    "https://x.test/path#fragment", 42]
        for url in bad_urls:
            config = {"version": 1, "endpoint": url, "timeout_seconds": 1, "api_key": "x"}
            with self.subTest(url=url), self.assertRaises(ConfigError):
                migrate_config(config)

    def test_numeric_types_and_ranges_are_strict(self):
        bad = [
            {"version": True, "endpoint": "https://x.test", "timeout_seconds": 1, "api_key": "x"},
            {"version": 1, "endpoint": "https://x.test", "timeout_seconds": True, "api_key": "x"},
            {"version": 1, "endpoint": "https://x.test", "timeout_seconds": 301, "api_key": "x"},
            {"version": 2, "service": {"url": "https://x.test", "timeout_ms": 0},
             "token": "x", "max_retries": 0},
            {"version": 2, "service": {"url": "https://x.test", "timeout_ms": 1},
             "token": "x", "max_retries": 10},
        ]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                migrate_config(config)

    def test_tokens_scheme_and_nested_mapping_types_are_strict(self):
        cases = [
            {"version": 1, "endpoint": "https://x.test", "timeout_seconds": 1, "api_key": ""},
            {"version": 2, "service": [], "token": "x", "max_retries": 0},
            {"version": 3, "service": {"url": "https://x.test", "timeout_ms": 1},
             "auth": {"scheme": "basic", "token": "x"}, "retry": {"max_attempts": 1}},
            {"version": 3, "service": {"url": "https://x.test", "timeout_ms": 1},
             "auth": {"scheme": "bearer", "token": 4}, "retry": {"max_attempts": 1}},
        ]
        for config in cases:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                migrate_config(config)

    def test_top_level_type_and_source_mutation(self):
        with self.assertRaises(TypeError):
            migrate_config([])
        source = {"version": 2, "service": {"url": "https://x.test", "timeout_ms": 1},
                  "token": "x", "max_retries": 0}
        before = copy.deepcopy(source)
        migrate_config(source)
        self.assertEqual(source, before)


unittest.main()
