import threading
import unittest

from lru_cache import LRUCache


class LRUCacheTests(unittest.TestCase):
    def test_get_refreshes_and_default_does_not(self):
        cache = LRUCache(3)
        cache.put("a", 1); cache.put("b", 2); cache.put("c", 3)
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.keys(), ("b", "c", "a"))
        marker = object()
        self.assertIs(cache.get("missing", marker), marker)
        self.assertEqual(cache.keys(), ("b", "c", "a"))
        with self.assertRaises(KeyError):
            cache.get("missing")

    def test_capacity_eviction_and_replacement(self):
        events = []
        cache = LRUCache(2, lambda *event: events.append(event))
        cache.put("a", 1); cache.put("b", None); cache.put("a", 3); cache.put("c", 4)
        self.assertEqual(cache.keys(), ("a", "c"))
        self.assertEqual(cache.get("a"), 3)
        self.assertEqual(events, [("b", None, "capacity")])

    def test_resize_and_clear_callback_order_and_committed_state(self):
        snapshots = []
        cache = None
        def callback(key, value, reason):
            snapshots.append((key, value, reason, cache.keys()))
        cache = LRUCache(4, callback)
        for key in "abcd": cache.put(key, ord(key))
        cache.get("b")
        cache.resize(2)
        self.assertEqual(cache.keys(), ("d", "b"))
        self.assertEqual([item[:3] for item in snapshots], [("a", 97, "resize"), ("c", 99, "resize")])
        self.assertTrue(all(item[3] == ("d", "b") for item in snapshots))
        snapshots.clear(); cache.clear()
        self.assertEqual([item[:3] for item in snapshots], [("d", 100, "clear"), ("b", 98, "clear")])
        self.assertEqual(len(cache), 0)

    def test_delete_is_not_eviction(self):
        events = []
        cache = LRUCache(2, lambda *event: events.append(event))
        cache.put("x", None)
        self.assertIsNone(cache.delete("x"))
        self.assertEqual(events, [])
        with self.assertRaises(KeyError):
            cache.delete("x")

    def test_validation(self):
        for capacity in (0, -1, True, 1.5):
            with self.subTest(capacity=capacity):
                with self.assertRaises((TypeError, ValueError)):
                    LRUCache(capacity)
        with self.assertRaises(TypeError):
            LRUCache(1, 42)
        cache = LRUCache(1)
        with self.assertRaises((TypeError, ValueError)):
            cache.resize(False)
        with self.assertRaises(TypeError):
            cache.put([], 1)

    def test_callback_exception_keeps_mutation(self):
        def callback(key, value, reason):
            raise RuntimeError((key, reason))
        cache = LRUCache(1, callback)
        cache.put("a", 1)
        with self.assertRaises(RuntimeError):
            cache.put("b", 2)
        self.assertEqual(cache.keys(), ("b",))

    def test_callback_does_not_hold_cache_lock(self):
        observations = []
        workers = []
        cache = None
        def callback(key, value, reason):
            finished = threading.Event()
            worker = threading.Thread(target=lambda: (cache.keys(), finished.set()))
            workers.append(worker)
            worker.start()
            worker.join(1)
            observations.append(finished.is_set())
        cache = LRUCache(1, callback)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(observations, [True])
        self.assertTrue(all(not worker.is_alive() for worker in workers))

    def test_threaded_operations_preserve_bound_and_contents(self):
        cache = LRUCache(8)
        barrier = threading.Barrier(5)
        def worker(offset):
            barrier.wait()
            for number in range(100):
                key = (offset + number) % 12
                cache.put(key, offset)
                cache.get(key)
        threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertLessEqual(len(cache), 8)
        self.assertEqual(len(cache.keys()), len(set(cache.keys())))


if __name__ == "__main__":
    unittest.main()
