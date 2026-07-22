import threading
import unittest

from event_journal import DuplicateEvent, EventJournal, JournalEvent


class EventJournalTests(unittest.TestCase):
    def test_append_duplicate_and_snapshot_order(self):
        journal = EventJournal()
        first = journal.append("a", {"value": 1})
        second = journal.append("b", "two")
        self.assertEqual(first, JournalEvent(1, "a", {"value": 1}))
        self.assertEqual(second.sequence, 2)
        with self.assertRaises(DuplicateEvent):
            journal.append("a", "replacement")
        self.assertEqual(journal.snapshot(), (first, second))

    def test_batch_is_atomic_for_all_failure_sources(self):
        journal = EventJournal()
        journal.append("existing", 0)
        with self.assertRaises(DuplicateEvent):
            journal.append_batch([("new", 1), ("existing", 2)])
        self.assertEqual([event.event_id for event in journal.snapshot()], ["existing"])
        with self.assertRaises(DuplicateEvent):
            journal.append_batch([("same", 1), ("same", 2)])

        failure = RuntimeError("source failed")

        def broken_source():
            yield "partial", 1
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            journal.append_batch(broken_source())
        self.assertIs(caught.exception, failure)
        self.assertEqual([event.event_id for event in journal.snapshot()], ["existing"])

    def test_replay_uses_stable_snapshot_and_sequence_filter(self):
        journal = EventJournal()
        journal.append_batch([("a", 1), ("b", 2), ("c", 3)])
        seen = []

        def apply(event):
            seen.append(event.event_id)
            if event.event_id == "b":
                journal.append("during-replay", 4)

        self.assertEqual(journal.replay(apply, after_sequence=1), 2)
        self.assertEqual(seen, ["b", "c"])
        self.assertEqual([event.event_id for event in journal.snapshot()], ["a", "b", "c", "during-replay"])

    def test_replay_preserves_handler_failure_and_validates_cursor(self):
        journal = EventJournal()
        journal.append_batch([("a", 1), ("b", 2), ("c", 3)])
        failure = LookupError("projection failed")
        seen = []

        def apply(event):
            seen.append(event.event_id)
            if event.event_id == "b":
                raise failure

        with self.assertRaises(LookupError) as caught:
            journal.replay(apply)
        self.assertIs(caught.exception, failure)
        self.assertEqual(seen, ["a", "b"])
        for invalid in (-1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    journal.replay(lambda event: seen.append("invalid"), invalid)
        self.assertEqual(seen, ["a", "b"])

    def test_concurrent_appends_keep_unique_contiguous_sequences(self):
        for round_number in range(30):
            journal = EventJournal()
            barrier = threading.Barrier(17)

            def append(index):
                barrier.wait()
                journal.append((round_number, index), index)

            threads = [threading.Thread(target=append, args=(i,)) for i in range(16)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            events = journal.snapshot()
            self.assertEqual([event.sequence for event in events], list(range(1, 17)))
            self.assertEqual({event.payload for event in events}, set(range(16)))


if __name__ == "__main__":
    unittest.main()
