import threading
import time
import unittest

from revisioned_state import VersionedState


class VersionedStateTests(unittest.TestCase):
    def test_initial_and_every_write_advances(self):
        state = VersionedState("same")
        self.assertEqual(state.snapshot(), (0, "same"))
        self.assertEqual(state.write("same"), 1)
        self.assertEqual(state.snapshot(), (1, "same"))
        self.assertEqual(state.write("next"), 2)

    def test_compare_and_set(self):
        state = VersionedState("a")
        self.assertEqual(state.compare_and_set(1, "wrong"), (False, 0))
        self.assertEqual(state.snapshot(), (0, "a"))
        self.assertEqual(state.compare_and_set(0, "b"), (True, 1))
        self.assertEqual(state.compare_and_set(0, "stale"), (False, 1))

    def test_wait_returns_immediately_for_newer_revision(self):
        state = VersionedState(object())
        value = object()
        state.write(value)
        revision, observed = state.wait_after(0, timeout=0)
        self.assertEqual(revision, 1)
        self.assertIs(observed, value)

    def test_write_wakes_all_waiters(self):
        state = VersionedState("old")
        rendezvous = threading.Barrier(4)
        results = []

        def waiter():
            rendezvous.wait()
            results.append(state.wait_after(0, timeout=1.0))

        threads = [threading.Thread(target=waiter) for _ in range(3)]
        for thread in threads:
            thread.start()
        rendezvous.wait()
        state.write("new")
        for thread in threads:
            thread.join(3.0)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results, [(1, "new")] * 3)

    def test_timeout_and_negative_timeout(self):
        state = VersionedState("unchanged")
        started = time.monotonic()
        self.assertIsNone(state.wait_after(0, timeout=0.04))
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.025)
        self.assertLess(elapsed, 2.0)
        with self.assertRaises(ValueError):
            state.wait_after(0, timeout=-0.01)

    def test_only_one_compare_and_set_succeeds(self):
        state = VersionedState("initial")
        rendezvous = threading.Barrier(3)
        results = []

        def contender(value):
            revision, _ = state.snapshot()
            rendezvous.wait()
            results.append(state.compare_and_set(revision, value))

        threads = [threading.Thread(target=contender, args=(value,)) for value in ("left", "right")]
        for thread in threads:
            thread.start()
        rendezvous.wait()
        for thread in threads:
            thread.join(3.0)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(success for success, _ in results), 1)
        self.assertEqual(sorted(revision for _, revision in results), [1, 1])

    def test_concurrent_writes_keep_revisions(self):
        state = VersionedState(None)

        def writer(prefix):
            for index in range(100):
                state.write((prefix, index))

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5.0)
            self.assertFalse(thread.is_alive())
        self.assertEqual(state.snapshot()[0], 400)


if __name__ == "__main__":
    unittest.main()
