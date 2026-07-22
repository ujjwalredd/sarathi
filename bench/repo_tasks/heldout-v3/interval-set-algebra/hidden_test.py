import unittest

from interval_set import IntervalSet


class IntervalSetTests(unittest.TestCase):
    def test_normalizes_overlap_adjacency_and_generator(self):
        source = [[5, 8], [1, 3], [3, 5], [12, 14], [13, 20]]
        value = IntervalSet((pair for pair in source))
        source[0][0] = 99
        self.assertEqual(value.intervals, ((1, 8), (12, 20)))
        self.assertEqual(tuple(value), ((1, 8), (12, 20)))
        self.assertEqual(len(value), 2)
        self.assertEqual(value.total_length, 15)

    def test_union_is_normalized_and_nonmutating(self):
        left = IntervalSet([(0, 2), (8, 10)])
        right = IntervalSet([(2, 8), (20, 21)])
        self.assertEqual(left.union(right), IntervalSet([(0, 10), (20, 21)]))
        self.assertEqual(left.intervals, ((0, 2), (8, 10)))
        self.assertEqual(right.intervals, ((2, 8), (20, 21)))

    def test_intersection_uses_half_open_boundaries(self):
        left = IntervalSet([(-5, 0), (2, 9), (20, 30)])
        right = IntervalSet([(0, 2), (4, 22)])
        self.assertEqual(left.intersection(right).intervals, ((4, 9), (20, 22)))
        self.assertEqual(IntervalSet([(0, 1)]).intersection(IntervalSet([(1, 2)])).intervals, ())

    def test_difference_can_split_and_span_intervals(self):
        left = IntervalSet([(0, 20), (30, 40)])
        right = IntervalSet([(-5, 3), (7, 11), (15, 35), (38, 50)])
        self.assertEqual(left.difference(right).intervals, ((3, 7), (11, 15), (35, 38)))
        self.assertEqual(right.difference(left).intervals, ((-5, 0), (20, 30), (40, 50)))

    def test_contains_points_and_large_endpoints(self):
        huge = 10 ** 30
        value = IntervalSet([(-huge, -huge + 2), (huge, huge + 3)])
        self.assertTrue(value.contains_point(-huge))
        self.assertFalse(value.contains_point(-huge + 2))
        self.assertTrue(value.contains_point(huge + 2))
        self.assertEqual(value.total_length, 5)
        with self.assertRaises(TypeError):
            value.contains_point(True)

    def test_constructor_validation(self):
        for bad, error in [([(1, 1)], ValueError), ([(2, 1)], ValueError), ([(True, 2)], TypeError), ([(1, 2, 3)], TypeError), ([1], TypeError), ("12", TypeError)]:
            with self.subTest(bad=bad):
                with self.assertRaises(error):
                    IntervalSet(bad)

    def test_operation_types_and_equality(self):
        value = IntervalSet([(1, 2)])
        for method in (value.union, value.intersection, value.difference):
            with self.assertRaises(TypeError):
                method([(1, 2)])
        self.assertNotEqual(value, ((1, 2),))


if __name__ == "__main__":
    unittest.main()
