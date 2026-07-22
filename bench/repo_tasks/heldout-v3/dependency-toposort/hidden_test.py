import unittest

from dependency_order import DependencyCycleError, topological_order


class Node:
    def __init__(self, label): self.label = label
    def __repr__(self): return f"Node({self.label})"


class DependencyOrderTests(unittest.TestCase):
    def test_dependencies_first_and_dependency_only_nodes(self):
        graph = {"app": ["db", "cache"], "worker": ["db"], "db": ["network"]}
        order = topological_order(graph)
        self.assertEqual(set(order), {"app", "worker", "db", "cache", "network"})
        self.assertLess(order.index("network"), order.index("db"))
        self.assertLess(order.index("db"), order.index("app"))
        self.assertLess(order.index("cache"), order.index("app"))

    def test_first_seen_ties_and_newly_eligible_jump(self):
        graph = {"target": ["first", "second"], "first": [], "second": [], "late": []}
        self.assertEqual(topological_order(graph), ("first", "second", "target", "late"))

    def test_unorderable_nodes_and_duplicate_dependencies(self):
        a, b, c = Node("a"), Node("b"), Node("c")
        graph = {a: [b, b], c: [b]}
        order = topological_order(graph)
        self.assertEqual(order, (b, a, c))
        self.assertEqual(len(order), 3)

    def test_deterministic_cycle_and_self_cycle(self):
        graph = {"stem": ["b"], "b": ["c"], "c": ["b"], "free": []}
        with self.assertRaises(DependencyCycleError) as caught:
            topological_order(graph)
        self.assertEqual(caught.exception.cycle, ("b", "c", "b"))
        marker = Node("self")
        with self.assertRaises(DependencyCycleError) as self_cycle:
            topological_order({marker: [marker]})
        self.assertEqual(self_cycle.exception.cycle, (marker, marker))

    def test_cycle_follows_lowest_first_seen_remaining_dependency(self):
        graph = {"a": ["b", "c"], "b": ["d"], "c": ["a"], "d": ["b"]}
        with self.assertRaises(DependencyCycleError) as caught:
            topological_order(graph)
        self.assertEqual(caught.exception.cycle, ("b", "d", "b"))

    def test_input_validation_and_generator_dependencies(self):
        self.assertEqual(topological_order({"a": (item for item in ["b"])}), ("b", "a"))
        for graph in ([], {"a": "bc"}, {"a": 1}, {[]: []} if False else None):
            if graph is None: continue
            with self.subTest(graph=graph):
                with self.assertRaises(TypeError):
                    topological_order(graph)
        with self.assertRaises(TypeError):
            topological_order({"a": [[]]})

    def test_long_chain_is_iterative(self):
        size = 3000
        graph = {number: [number + 1] for number in range(size)}
        graph[size] = []
        order = topological_order(graph)
        self.assertEqual(len(order), size + 1)
        self.assertEqual(order[0], size)
        self.assertEqual(order[-1], 0)


if __name__ == "__main__":
    unittest.main()
