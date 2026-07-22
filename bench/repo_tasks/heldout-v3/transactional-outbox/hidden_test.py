import threading
import unittest

from transactional_outbox import OutboxEvent, TransactionalOutbox


class TransactionalOutboxTests(unittest.TestCase):
    def test_commit_is_visible_as_state_and_ordered_events(self):
        store = TransactionalOutbox()
        with store.transaction() as tx:
            tx.set("status", "paid")
            tx.enqueue("audit", {"id": 7})
            tx.enqueue("email", "receipt")
        state, pending = store.snapshot()
        self.assertEqual(state, {"status": "paid"})
        self.assertEqual(pending, (
            OutboxEvent(1, "audit", {"id": 7}),
            OutboxEvent(2, "email", "receipt"),
        ))
        state["status"] = "tampered"
        self.assertEqual(store.snapshot()[0], {"status": "paid"})

    def test_exception_rolls_back_everything_and_transaction_closes(self):
        store = TransactionalOutbox()
        failure = RuntimeError("abort")
        with self.assertRaises(RuntimeError) as caught:
            with store.transaction() as tx:
                tx.set("partial", True)
                tx.enqueue("bad", 1)
                raise failure
        self.assertIs(caught.exception, failure)
        self.assertEqual(store.snapshot(), ({}, ()))
        with self.assertRaises(RuntimeError):
            tx.set("late", True)
        with self.assertRaises(TypeError):
            with store.transaction() as invalid:
                invalid.set("partial", True)
                invalid.set([], "unhashable")
                invalid.enqueue("must-not-commit", 1)
        self.assertEqual(store.snapshot(), ({}, ()))

    def test_handler_failure_preserves_failed_event_and_tail(self):
        store = TransactionalOutbox()
        with store.transaction() as tx:
            for number in range(1, 4):
                tx.enqueue("work", number)
        seen = []
        failure = LookupError("consumer failed")

        def handler(event):
            seen.append(event.sequence)
            if event.sequence == 2:
                raise failure

        with self.assertRaises(LookupError) as caught:
            store.drain(handler)
        self.assertIs(caught.exception, failure)
        self.assertEqual([event.sequence for event in store.snapshot()[1]], [2, 3])
        self.assertEqual(store.drain(lambda event: seen.append(event.sequence)), 2)
        self.assertEqual(seen, [1, 2, 2, 3])
        self.assertEqual(store.snapshot()[1], ())

    def test_limit_validation_and_zero_limit_do_not_deliver(self):
        store = TransactionalOutbox()
        with store.transaction() as tx:
            tx.enqueue("topic", "payload")
        for invalid in (-1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    store.drain(lambda event: None, invalid)
        self.assertEqual(store.drain(lambda event: None, 0), 0)
        self.assertEqual(len(store.snapshot()[1]), 1)

    def test_concurrent_commits_have_contiguous_sequences(self):
        for round_number in range(30):
            store = TransactionalOutbox()
            barrier = threading.Barrier(13)

            def commit(index):
                barrier.wait()
                with store.transaction() as tx:
                    tx.set(index, round_number)
                    tx.enqueue("item", index)

            threads = [threading.Thread(target=commit, args=(i,)) for i in range(12)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            state, pending = store.snapshot()
            self.assertEqual(state, {i: round_number for i in range(12)})
            self.assertEqual([event.sequence for event in pending], list(range(1, 13)))
            self.assertEqual({event.payload for event in pending}, set(range(12)))


if __name__ == "__main__":
    unittest.main()
