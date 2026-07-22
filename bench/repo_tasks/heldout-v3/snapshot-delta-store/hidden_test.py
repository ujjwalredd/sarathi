import threading
import unittest

from snapshot_delta_store import Conflict, DELETE, SnapshotDeltaStore


class SnapshotDeltaStoreTests(unittest.TestCase):
    def test_snapshot_is_deeply_isolated_and_delete_works(self):
        store = SnapshotDeltaStore({"nested": {"count": 1}, "remove": True})
        first = store.snapshot()
        first.data["nested"]["count"] = 99
        first.data["new"] = "tamper"
        self.assertEqual(store.snapshot().data, {"nested": {"count": 1}, "remove": True})
        self.assertEqual(store.apply({"remove": DELETE, "added": [1]}, 0), 1)
        self.assertEqual(store.snapshot().data, {"nested": {"count": 1}, "added": [1]})

    def test_stale_commit_is_rejected_without_mutation(self):
        store = SnapshotDeltaStore()
        store.apply({"a": 1}, 0)
        before = store.snapshot()
        with self.assertRaises(Conflict):
            store.apply({"a": 2, "b": 3}, 0)
        self.assertEqual(store.snapshot(), before)
        self.assertEqual(len(store.deltas_since(0)), 1)

    def test_copy_failure_rolls_back_entire_commit(self):
        store = SnapshotDeltaStore({"stable": 1})
        failure = RuntimeError("cannot copy")

        class Exploding:
            def __deepcopy__(self, memo):
                raise failure

        with self.assertRaises(RuntimeError) as caught:
            store.apply({"partial": 2, "bad": Exploding()}, 0)
        self.assertIs(caught.exception, failure)
        self.assertEqual(store.snapshot().version, 0)
        self.assertEqual(store.snapshot().data, {"stable": 1})
        self.assertEqual(store.deltas_since(0), ())

    def test_deltas_are_ordered_and_deeply_isolated(self):
        store = SnapshotDeltaStore()
        store.apply({"value": [1]}, 0)
        store.apply({}, 1)
        store.apply({"value": [2]}, 2)
        deltas = store.deltas_since(0)
        self.assertEqual([delta.version for delta in deltas], [1, 2, 3])
        self.assertEqual(deltas[1].changes, {})
        deltas[0].changes["value"].append(99)
        self.assertEqual(store.deltas_since(0)[0].changes, {"value": [1]})
        self.assertEqual(store.deltas_since(2)[0].changes, {"value": [2]})
        for invalid in (-1, 4, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    store.deltas_since(invalid)

    def test_concurrent_compare_and_set_has_one_winner(self):
        for round_number in range(40):
            store = SnapshotDeltaStore()
            barrier = threading.Barrier(17)
            winners = []
            conflicts = []

            def commit(index):
                barrier.wait()
                try:
                    store.apply({"winner": index}, 0)
                    winners.append(index)
                except Conflict:
                    conflicts.append(index)

            threads = [threading.Thread(target=commit, args=(i,)) for i in range(16)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(conflicts), 15)
            self.assertEqual(store.snapshot().data, {"winner": winners[0]})
            self.assertEqual([delta.version for delta in store.deltas_since(0)], [1])


if __name__ == "__main__":
    unittest.main()
