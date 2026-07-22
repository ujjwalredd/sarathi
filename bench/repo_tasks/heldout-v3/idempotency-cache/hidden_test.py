import threading
import unittest

from idempotency_cache import IdempotencyCache


class IdempotencyCacheTests(unittest.TestCase):
    def test_success_and_false_values_are_cached(self):
        cache = IdempotencyCache()
        calls = []
        value = object()
        self.assertIs(cache.compute("object", lambda: calls.append(1) or value), value)
        self.assertIs(cache.compute("object", lambda: object()), value)
        self.assertIsNone(cache.compute("none", lambda: calls.append(2)))
        self.assertIsNone(cache.compute("none", lambda: calls.append(3)))
        self.assertEqual(calls, [1, 2])

    def test_exception_is_shared_but_not_cached(self):
        cache = IdempotencyCache()
        failure = LookupError("failed")
        entered = threading.Event()
        release = threading.Event()
        caught = []
        calls = []

        def operation():
            calls.append(threading.get_ident())
            entered.set()
            release.wait()
            raise failure

        def invoke():
            try:
                cache.compute("key", operation)
            except Exception as error:
                caught.append(error)

        owner = threading.Thread(target=invoke)
        owner.start()
        self.assertTrue(entered.wait(1))
        waiters = [threading.Thread(target=invoke) for _ in range(12)]
        for waiter in waiters:
            waiter.start()
        release.set()
        owner.join()
        for waiter in waiters:
            waiter.join()
        self.assertEqual(len(caught), 13)
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(error is failure for error in caught))
        self.assertEqual(cache.compute("key", lambda: "retry"), "retry")

    def test_same_key_concurrent_success_runs_once(self):
        cache = IdempotencyCache()
        entered = threading.Event()
        release = threading.Event()
        calls = []
        results = []

        def operation():
            calls.append(threading.get_ident())
            entered.set()
            release.wait()
            return "value"

        owner = threading.Thread(target=lambda: results.append(cache.compute("same", operation)))
        owner.start()
        self.assertTrue(entered.wait(1))
        barrier = threading.Barrier(25)

        def waiter():
            barrier.wait()
            results.append(cache.compute("same", operation))

        threads = [threading.Thread(target=waiter) for _ in range(24)]
        for thread in threads:
            thread.start()
        barrier.wait()
        release.set()
        owner.join()
        for thread in threads:
            thread.join()
        self.assertEqual(calls, [calls[0]])
        self.assertEqual(results, ["value"] * 25)

    def test_different_keys_are_not_globally_serialized(self):
        cache = IdempotencyCache()
        rendezvous = threading.Barrier(2)
        results = {}

        def invoke(key):
            def operation():
                rendezvous.wait(timeout=1)
                return key.upper()
            results[key] = cache.compute(key, operation)

        threads = [threading.Thread(target=invoke, args=(key,)) for key in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, {"a": "A", "b": "B"})

    def test_invalidate_affects_only_completed_value(self):
        cache = IdempotencyCache()
        self.assertFalse(cache.invalidate("missing"))
        entered = threading.Event()
        release = threading.Event()
        result = []

        def operation():
            entered.set()
            release.wait()
            return 3

        thread = threading.Thread(target=lambda: result.append(cache.compute("key", operation)))
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertFalse(cache.invalidate("key"))
        release.set()
        thread.join()
        self.assertEqual(result, [3])
        self.assertTrue(cache.invalidate("key"))
        self.assertFalse(cache.invalidate("key"))
        self.assertEqual(cache.compute("key", lambda: 4), 4)


if __name__ == "__main__":
    unittest.main()
