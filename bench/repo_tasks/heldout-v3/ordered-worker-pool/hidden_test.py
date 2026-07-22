import threading
import unittest

from ordered_worker_pool import ordered_map


class OrderedWorkerPoolTests(unittest.TestCase):
    def test_reverse_completion_still_returns_input_order(self):
        count = 6
        started = [threading.Event() for _ in range(count)]
        release = [threading.Event() for _ in range(count)]
        finished = [threading.Event() for _ in range(count)]
        outcome = []
        errors = []

        def work(index):
            started[index].set()
            release[index].wait()
            finished[index].set()
            return {"index": index}

        def invoke():
            try:
                outcome.extend(ordered_map(work, range(count), count))
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=invoke)
        thread.start()
        all_started = all(event.wait(1) for event in started)
        if all_started:
            for index in reversed(range(count)):
                release[index].set()
                finished[index].wait(1)
        else:
            for event in release:
                event.set()
        thread.join()
        self.assertTrue(all_started)
        self.assertEqual(errors, [])
        self.assertEqual(outcome, [{"index": index} for index in range(count)])

    def test_concurrency_is_bounded_but_real(self):
        lock = threading.Lock()
        three_active = threading.Event()
        release = threading.Event()
        active = 0
        peak = 0

        def work(item):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 3:
                    three_active.set()
            release.wait()
            with lock:
                active -= 1
            return item

        output = []
        thread = threading.Thread(
            target=lambda: output.extend(ordered_map(work, range(12), 3)))
        thread.start()
        reached_three = three_active.wait(1)
        release.set()
        thread.join()
        self.assertTrue(reached_three)
        self.assertEqual(peak, 3)
        self.assertEqual(output, list(range(12)))

    def test_exception_object_is_preserved(self):
        failure = LookupError("worker failed")

        def work(item):
            if item == 2:
                raise failure
            return item

        with self.assertRaises(LookupError) as caught:
            ordered_map(work, [0, 1, 2, 3], 2)
        self.assertIs(caught.exception, failure)

    def test_generator_duplicates_and_empty_input(self):
        consumed = []

        def source():
            for item in [3, 1, 3, 2]:
                consumed.append(item)
                yield item

        self.assertEqual(ordered_map(lambda item: (item, object()), source(), 2)[0][0], 3)
        self.assertEqual(consumed, [3, 1, 3, 2])
        self.assertEqual([value for value, marker in ordered_map(lambda x: (x, None), [3, 1, 3, 2], 2)], [3, 1, 3, 2])
        self.assertEqual(ordered_map(lambda item: item, [], 2), [])

    def test_invalid_worker_count_does_not_consume_iterable(self):
        consumed = []

        def source():
            consumed.append(True)
            yield 1

        for invalid in (0, -1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    ordered_map(lambda item: item, source(), invalid)
        self.assertEqual(consumed, [])


if __name__ == "__main__":
    unittest.main()
