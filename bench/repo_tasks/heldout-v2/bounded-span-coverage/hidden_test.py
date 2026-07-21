import unittest

from coverage_rollup import aggregate_coverage


class AggregateCoverageTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(aggregate_coverage([], max_spans=0, max_groups=0), ())

    def test_merges_unsorted_overlapping_and_touching(self):
        spans = [("api", 20, 22), ("api", 4, 9), ("api", 0, 3), ("api", 3, 5)]
        self.assertEqual(
            aggregate_coverage(spans, max_spans=4, max_groups=1),
            (("api", 11, ((0, 9), (20, 22))),),
        )

    def test_nested_and_separated_intervals(self):
        spans = [("worker", 10, 20), ("worker", 12, 13), ("worker", 2, 3), ("worker", 1, 2)]
        self.assertEqual(
            aggregate_coverage(spans, max_spans=10, max_groups=2),
            (("worker", 12, ((1, 3), (10, 20))),),
        )

    def test_sorts_groups(self):
        self.assertEqual(
            aggregate_coverage([("z", 0, 1), ("a", 5, 8)], max_spans=2, max_groups=2),
            (("a", 3, ((5, 8),)), ("z", 1, ((0, 1),))),
        )

    def test_span_overflow_consumes_exactly_one_extra(self):
        seen = []

        def records():
            for record in [("a", 0, 1), ("a", 1, 2), ("bad overflow record",), ("a", 3, 4)]:
                seen.append(record)
                yield record

        with self.assertRaises(OverflowError):
            aggregate_coverage(records(), max_spans=2, max_groups=1)
        self.assertEqual(len(seen), 3)

    def test_group_limit_counts_only_distinct_resources(self):
        self.assertEqual(
            aggregate_coverage([("a", 0, 1), ("a", 2, 3)], max_spans=2, max_groups=1),
            (("a", 2, ((0, 1), (2, 3))),),
        )
        with self.assertRaises(OverflowError):
            aggregate_coverage([("a", 0, 1), ("a", 2, 3), ("b", 0, 1)], max_spans=3, max_groups=1)

    def test_invalid_limits_before_consumption(self):
        class Bomb:
            def __iter__(self):
                raise AssertionError("input was consumed")

        with self.assertRaises(TypeError):
            aggregate_coverage(Bomb(), max_spans=True, max_groups=1)
        with self.assertRaises(ValueError):
            aggregate_coverage(Bomb(), max_spans=1, max_groups=-1)

    def test_rejects_invalid_accepted_records(self):
        invalid = [
            ["a", 0, 1], ("", 0, 1), ("é", 0, 1), ("a", False, 1),
            ("a", 0, True), ("a", 1, 1), ("a", -1, 2), ("a", 0, 2**63),
        ]
        for record in invalid:
            expected = TypeError if (
                type(record) is not tuple
                or (type(record) is tuple and len(record) == 3 and any(
                    type(value) is not expected_type
                    for value, expected_type in zip(record, (str, int, int))
                ))
            ) else ValueError
            with self.subTest(record=record), self.assertRaises(expected):
                aggregate_coverage([record], max_spans=1, max_groups=1)


if __name__ == "__main__":
    unittest.main()
