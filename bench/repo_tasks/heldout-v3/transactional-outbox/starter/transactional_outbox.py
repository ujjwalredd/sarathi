"""In-memory state and outbox."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OutboxEvent:
    sequence: int
    topic: object
    payload: object


class _Transaction:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def set(self, key, value):
        self.store._state[key] = value

    def enqueue(self, topic, payload):
        sequence = len(self.store._pending) + 1
        self.store._pending.append(OutboxEvent(sequence, topic, payload))

    def __exit__(self, exc_type, exc, traceback):
        return False


class TransactionalOutbox:
    def __init__(self):
        self._state = {}
        self._pending = []

    def transaction(self):
        return _Transaction(self)

    def snapshot(self):
        return self._state, tuple(self._pending)

    def drain(self, handler, limit=None):
        delivered = 0
        while self._pending and (limit is None or delivered < limit):
            event = self._pending.pop(0)
            handler(event)
            delivered += 1
        return delivered
