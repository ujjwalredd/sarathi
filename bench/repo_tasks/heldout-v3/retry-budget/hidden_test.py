import threading
import unittest

from retry_budget import RetryBudget, retry


class RetryBudgetTests(unittest.TestCase):
    def test_retry_consumes_tokens_and_uses_numbered_backoff(self):
        budget = RetryBudget(4, 2)
        failures = [OSError("first"), OSError("second")]
        attempts = []
        sleeps = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) <= 2:
                raise failures[len(attempts) - 1]
            return None

        result = retry(
            operation,
            budget=budget,
            max_attempts=4,
            backoff_ns=lambda retry_number: retry_number * 5,
            sleep_ns=sleeps.append,
        )
        self.assertIsNone(result)
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(sleeps, [5, 10])
        self.assertEqual(budget.available, 0)

    def test_exhaustion_and_attempt_limit_preserve_exact_failure(self):
        empty = RetryBudget(2, 0)
        failure = LookupError("no retry capacity")
        with self.assertRaises(LookupError) as caught:
            retry(lambda: (_ for _ in ()).throw(failure), budget=empty, max_attempts=3)
        self.assertIs(caught.exception, failure)
        self.assertEqual(empty.available, 0)

        one = RetryBudget(3, 3)
        final = RuntimeError("only attempt")
        with self.assertRaises(RuntimeError) as caught:
            retry(lambda: (_ for _ in ()).throw(final), budget=one, max_attempts=1)
        self.assertIs(caught.exception, final)
        self.assertEqual(one.available, 3)

    def test_non_retryable_and_backoff_failure_do_not_consume(self):
        budget = RetryBudget(3)
        non_retryable = KeyError("stop")
        with self.assertRaises(KeyError) as caught:
            retry(
                lambda: (_ for _ in ()).throw(non_retryable),
                budget=budget,
                max_attempts=3,
                retryable=(OSError,),
            )
        self.assertIs(caught.exception, non_retryable)
        self.assertEqual(budget.available, 3)

        backoff_failure = ValueError("bad policy")
        with self.assertRaises(ValueError) as caught:
            retry(
                lambda: (_ for _ in ()).throw(OSError("retryable")),
                budget=budget,
                max_attempts=2,
                backoff_ns=lambda number: (_ for _ in ()).throw(backoff_failure),
            )
        self.assertIs(caught.exception, backoff_failure)
        self.assertEqual(budget.available, 3)

    def test_validation_and_replenishment_are_atomic(self):
        budget = RetryBudget(5, 1)
        self.assertEqual(budget.replenish(10), 5)
        for invalid in (0, -1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    budget.replenish(invalid)
        self.assertEqual(budget.available, 5)
        with self.assertRaises(ValueError):
            retry(
                lambda: (_ for _ in ()).throw(OSError("retry")),
                budget=budget,
                max_attempts=2,
                backoff_ns=lambda number: True,
            )
        self.assertEqual(budget.available, 5)
        for invalid in (0, -1, 1.5, True):
            with self.subTest(max_attempts=invalid):
                calls = []
                with self.assertRaises(ValueError):
                    retry(lambda: calls.append(True), budget=budget, max_attempts=invalid)
                self.assertEqual(calls, [])

    def test_concurrent_consumers_cannot_overspend(self):
        for round_number in range(40):
            budget = RetryBudget(9)
            barrier = threading.Barrier(33)
            outcomes = []

            def consume():
                barrier.wait()
                outcomes.append(budget.try_consume())

            threads = [threading.Thread(target=consume) for _ in range(32)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(len(outcomes), 32)
            self.assertEqual(outcomes.count(True), 9)
            self.assertEqual(budget.available, 0)


if __name__ == "__main__":
    unittest.main()
