import threading
import unittest

from token_bucket import TokenBucket


class FakeClock:
    def __init__(self, value=0):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class TokenBucketTests(unittest.TestCase):
    def test_fractional_refill_survives_failed_acquisition(self):
        clock = FakeClock()
        bucket = TokenBucket(4, 0.5, clock)
        self.assertTrue(bucket.try_acquire(4))
        clock.value = 1
        self.assertFalse(bucket.try_acquire())
        self.assertAlmostEqual(bucket.available, 0.5)
        clock.value = 2
        self.assertTrue(bucket.try_acquire())
        self.assertAlmostEqual(bucket.available, 0.0)

    def test_refill_is_capped_and_uses_elapsed_monotonic_time(self):
        clock = FakeClock(10)
        bucket = TokenBucket(3, 0.25, clock)
        bucket.try_acquire(2)
        clock.value = 14
        self.assertAlmostEqual(bucket.available, 2.0)
        clock.value = 100
        self.assertAlmostEqual(bucket.available, 3.0)
        self.assertTrue(bucket.try_acquire(3))

    def test_each_operation_reads_clock_once(self):
        clock = FakeClock()
        bucket = TokenBucket(2, 1, clock)
        initial_calls = clock.calls
        bucket.try_acquire()
        self.assertEqual(clock.calls, initial_calls + 1)
        unused = bucket.available
        self.assertEqual(clock.calls, initial_calls + 2)

    def test_invalid_values_preserve_state_and_skip_clock(self):
        for args in ((0, 1), (1, 0), (True, 1), (1, float("inf"))):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    TokenBucket(*args, FakeClock())
        clock = FakeClock()
        bucket = TokenBucket(2, 1, clock)
        before_calls = clock.calls
        for amount in (0, -1, True, float("nan")):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    bucket.try_acquire(amount)
        self.assertEqual(clock.calls, before_calls)
        self.assertAlmostEqual(bucket.available, 2.0)

    def test_concurrent_consumption_never_exceeds_capacity(self):
        for round_number in range(40):
            clock = FakeClock(round_number)
            bucket = TokenBucket(7, 1, clock)
            barrier = threading.Barrier(33)
            outcomes = []

            def consume():
                barrier.wait()
                outcomes.append(bucket.try_acquire())

            threads = [threading.Thread(target=consume) for _ in range(32)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(len(outcomes), 32)
            self.assertEqual(outcomes.count(True), 7)
            self.assertAlmostEqual(bucket.available, 0.0)


if __name__ == "__main__":
    unittest.main()
