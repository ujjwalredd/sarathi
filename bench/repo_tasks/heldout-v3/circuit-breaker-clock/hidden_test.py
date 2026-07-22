import threading
import unittest

from circuit_breaker import CircuitBreaker, CircuitOpen


class FakeClock:
    def __init__(self, value=0):
        self.value = value

    def __call__(self):
        return self.value


class CircuitBreakerTests(unittest.TestCase):
    def test_failures_are_preserved_and_threshold_opens(self):
        clock = FakeClock(4)
        breaker = CircuitBreaker(2, 10, clock)
        first = LookupError("first")
        second = LookupError("second")
        with self.assertRaises(LookupError) as caught:
            breaker.call(lambda: (_ for _ in ()).throw(first))
        self.assertIs(caught.exception, first)
        self.assertEqual(breaker.state, "closed")
        with self.assertRaises(LookupError) as caught:
            breaker.call(lambda: (_ for _ in ()).throw(second))
        self.assertIs(caught.exception, second)
        self.assertEqual(breaker.state, "open")

    def test_open_rejects_without_invocation_until_exact_deadline(self):
        clock = FakeClock()
        breaker = CircuitBreaker(1, 5, clock)
        with self.assertRaises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("bad")))
        calls = []
        clock.value = 4
        with self.assertRaises(CircuitOpen):
            breaker.call(lambda: calls.append("early"))
        self.assertEqual(calls, [])
        clock.value = 5
        self.assertEqual(breaker.call(lambda: "recovered"), "recovered")
        self.assertEqual(breaker.state, "closed")

    def test_success_resets_consecutive_failures(self):
        for args in ((0, 1), (1, 0), (True, 1), (1, 1.5)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    CircuitBreaker(*args, FakeClock())
        clock = FakeClock()
        breaker = CircuitBreaker(2, 10, clock)
        for message in ("one", "two"):
            with self.assertRaises(RuntimeError):
                breaker.call(lambda message=message: (_ for _ in ()).throw(RuntimeError(message)))
            if message == "one":
                self.assertEqual(breaker.call(lambda: 7), 7)
        self.assertEqual(breaker.state, "closed")

    def test_only_one_half_open_probe_runs(self):
        clock = FakeClock()
        breaker = CircuitBreaker(1, 10, clock)
        with self.assertRaises(OSError):
            breaker.call(lambda: (_ for _ in ()).throw(OSError("down")))
        clock.value = 10
        entered = threading.Event()
        release = threading.Event()
        outcome = []

        def probe():
            entered.set()
            release.wait()
            return "ok"

        thread = threading.Thread(target=lambda: outcome.append(breaker.call(probe)))
        thread.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(breaker.state, "half_open")
        with self.assertRaises(CircuitOpen):
            breaker.call(lambda: "must not run")
        release.set()
        thread.join()
        self.assertEqual(outcome, ["ok"])
        self.assertEqual(breaker.state, "closed")

    def test_failed_probe_starts_fresh_timeout(self):
        clock = FakeClock()
        breaker = CircuitBreaker(1, 5, clock)
        with self.assertRaises(KeyError):
            breaker.call(lambda: (_ for _ in ()).throw(KeyError("initial")))
        clock.value = 5
        failure = KeyError("probe")
        clock.value = 6
        with self.assertRaises(KeyError) as caught:
            breaker.call(lambda: (_ for _ in ()).throw(failure))
        self.assertIs(caught.exception, failure)
        clock.value = 10
        with self.assertRaises(CircuitOpen):
            breaker.call(lambda: None)
        clock.value = 11
        self.assertEqual(breaker.call(lambda: "up"), "up")


if __name__ == "__main__":
    unittest.main()
