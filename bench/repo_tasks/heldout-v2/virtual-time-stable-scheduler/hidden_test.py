import math
import unittest

from deterministic_scheduler import DeterministicScheduler


class DeterministicSchedulerTests(unittest.TestCase):
    def test_due_order_and_final_time(self):
        scheduler = DeterministicScheduler()
        observed = []

        def record(label):
            observed.append((label, scheduler.now))

        scheduler.schedule(3, record, "third")
        scheduler.schedule(1, record, "first")
        scheduler.schedule(2, record, "second")
        self.assertEqual(scheduler.pending, 3)
        scheduler.run_until(3)
        self.assertEqual(observed, [("first", 1.0), ("second", 2.0), ("third", 3.0)])
        self.assertEqual(scheduler.now, 3.0)
        self.assertEqual(scheduler.pending, 0)

    def test_equal_times_use_insertion_order(self):
        scheduler = DeterministicScheduler(10)
        observed = []
        for label in ["a", "b", "c", "d"]:
            scheduler.schedule(2, observed.append, label)
        scheduler.run_until(12)
        self.assertEqual(observed, ["a", "b", "c", "d"])

    def test_nested_zero_delay_follows_existing_work(self):
        scheduler = DeterministicScheduler()
        observed = []

        def first():
            observed.append(("first", scheduler.now))
            scheduler.schedule(0, observed.append, ("nested", scheduler.now))

        scheduler.schedule(1, first)
        scheduler.schedule(1, observed.append, ("existing", 1.0))
        scheduler.run_until(1)
        self.assertEqual(observed, [("first", 1.0), ("existing", 1.0), ("nested", 1.0)])

    def test_cancellation_owned_and_idempotent(self):
        first = DeterministicScheduler()
        second = DeterministicScheduler()
        observed = []
        handle = first.schedule(1, observed.append, "bad")
        self.assertFalse(second.cancel(handle))
        self.assertTrue(first.cancel(handle))
        self.assertFalse(first.cancel(handle))
        self.assertFalse(first.cancel(object()))
        self.assertEqual(first.pending, 0)
        first.run_until(2)
        self.assertEqual(observed, [])

    def test_exception_preserves_time_and_work(self):
        scheduler = DeterministicScheduler()
        observed = []

        def fail():
            observed.append(("fail", scheduler.now))
            raise ValueError("boom")

        failed = scheduler.schedule(2, fail)
        scheduler.schedule(2, observed.append, ("same-time", 2.0))
        scheduler.schedule(3, observed.append, ("later", 3.0))
        with self.assertRaisesRegex(ValueError, "boom"):
            scheduler.run_until(5)
        self.assertFalse(scheduler.cancel(failed))
        self.assertEqual(scheduler.now, 2.0)
        self.assertEqual(scheduler.pending, 2)
        scheduler.run_until(5)
        self.assertEqual(observed, [("fail", 2.0), ("same-time", 2.0), ("later", 3.0)])

    def test_nested_delay_uses_callback_time(self):
        scheduler = DeterministicScheduler()
        observed = []

        def at_two():
            observed.append(("outer", scheduler.now))
            scheduler.schedule(3, observed.append, ("inner", 5.0))

        scheduler.schedule(2, at_two)
        scheduler.run_until(4)
        self.assertEqual(observed, [("outer", 2.0)])
        self.assertEqual(scheduler.pending, 1)
        scheduler.run_until(5)
        self.assertEqual(observed, [("outer", 2.0), ("inner", 5.0)])

    def test_numeric_validation_and_backward_run(self):
        with self.assertRaises(TypeError):
            DeterministicScheduler(True)
        with self.assertRaises(ValueError):
            DeterministicScheduler(math.nan)
        scheduler = DeterministicScheduler(2)
        for bad in (True, "1", None):
            with self.subTest(delay=bad), self.assertRaises(TypeError):
                scheduler.schedule(bad, lambda: None)
        for bad in (-1, math.inf, math.nan):
            with self.subTest(delay=bad), self.assertRaises(ValueError):
                scheduler.schedule(bad, lambda: None)
        with self.assertRaises(ValueError):
            scheduler.run_until(1)
        with self.assertRaises(TypeError):
            scheduler.run_until("3")
        with self.assertRaises(ValueError):
            scheduler.run_until(math.inf)

    def test_reentrant_run_rejected(self):
        scheduler = DeterministicScheduler()
        observed = []

        def callback():
            observed.append("outer")
            with self.assertRaises(RuntimeError):
                scheduler.run_until(scheduler.now)
            scheduler.schedule(0, observed.append, "nested")

        scheduler.schedule(0, callback)
        scheduler.run_until(0)
        self.assertEqual(observed, ["outer", "nested"])
        self.assertEqual(scheduler.pending, 0)


if __name__ == "__main__":
    unittest.main()
