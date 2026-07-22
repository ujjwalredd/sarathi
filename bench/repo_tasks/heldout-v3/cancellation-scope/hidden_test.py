import threading
import unittest

from cancellation_scope import CancellationScope, Cancelled


class CancellationScopeTests(unittest.TestCase):
    def test_parent_cancellation_wakes_nested_descendant(self):
        root = CancellationScope()
        child = root.child()
        grandchild = child.child()
        ready = threading.Event()
        outcome = []

        def wait_for_cancel():
            ready.set()
            outcome.append(grandchild.wait())

        thread = threading.Thread(target=wait_for_cancel)
        thread.start()
        self.assertTrue(ready.wait(1))
        self.assertTrue(root.cancel())
        thread.join(0.5)
        was_stuck = thread.is_alive()
        if was_stuck:
            grandchild.cancel()
            thread.join(1)
        self.assertFalse(was_stuck)
        self.assertEqual(outcome, [True])
        self.assertTrue(child.is_cancelled)
        self.assertTrue(grandchild.is_cancelled)

    def test_child_cancellation_is_isolated_and_idempotent(self):
        root = CancellationScope()
        first = root.child()
        second = root.child()
        self.assertTrue(first.cancel())
        self.assertFalse(first.cancel())
        self.assertTrue(first.is_cancelled)
        self.assertFalse(root.is_cancelled)
        self.assertFalse(second.is_cancelled)
        self.assertFalse(second.wait(0))

    def test_late_child_starts_cancelled(self):
        root = CancellationScope()
        root.cancel()
        child = root.child()
        grandchild = child.child()
        self.assertTrue(child.is_cancelled)
        self.assertTrue(child.wait(0))
        self.assertTrue(grandchild.is_cancelled)
        self.assertTrue(grandchild.wait(0))

    def test_checkpoint_raises_only_after_cancellation(self):
        scope = CancellationScope()
        self.assertIsNone(scope.checkpoint())
        scope.cancel()
        with self.assertRaises(Cancelled):
            scope.checkpoint()

    def test_child_creation_cancel_race_never_leaks_live_child(self):
        for round_number in range(100):
            root = CancellationScope()
            barrier = threading.Barrier(3)
            children = []

            def create():
                barrier.wait()
                children.append(root.child())

            def cancel():
                barrier.wait()
                root.cancel()

            threads = [threading.Thread(target=create), threading.Thread(target=cancel)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(len(children), 1)
            self.assertTrue(root.is_cancelled)
            self.assertTrue(children[0].is_cancelled)
            self.assertTrue(children[0].wait(0))


if __name__ == "__main__":
    unittest.main()
