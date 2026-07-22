"""Append-only in-memory event journal."""

from dataclasses import dataclass


class DuplicateEvent(ValueError):
    pass


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    event_id: object
    payload: object


class EventJournal:
    def __init__(self):
        self._events = []
        self._ids = set()

    def append(self, event_id, payload):
        if event_id in self._ids:
            raise DuplicateEvent(event_id)
        event = JournalEvent(len(self._events) + 1, event_id, payload)
        self._events.append(event)
        self._ids.add(event_id)
        return event

    def append_batch(self, entries):
        return tuple(self.append(event_id, payload) for event_id, payload in entries)

    def snapshot(self):
        return tuple(self._events)

    def replay(self, apply, after_sequence=0):
        count = 0
        for event in self._events:
            if event.sequence > after_sequence:
                apply(event)
                count += 1
        return count
