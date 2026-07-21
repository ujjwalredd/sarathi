from dataclasses import dataclass


@dataclass(eq=False)
class _Handle:
    owner: object
    sequence: int
    state: str = "pending"


class DeterministicScheduler:
    def __init__(self, start=0):
        self._now = float(start)
        self._owner = object()
        self._sequence = 0
        self._events = []

    @property
    def now(self):
        return self._now

    @property
    def pending(self):
        return sum(handle.state == "pending" for _, handle, _, _, _ in self._events)

    def schedule(self, delay, callback, *args, **kwargs):
        handle = _Handle(self._owner, self._sequence)
        self._sequence += 1
        self._events.append((self._now + float(delay), handle, callback, args, kwargs))
        return handle

    def cancel(self, handle):
        if not isinstance(handle, _Handle) or handle.owner is not self._owner or handle.state != "pending":
            return False
        handle.state = "cancelled"
        return True

    def run_until(self, target):
        target = float(target)
        self._now = target
        ready = [event for event in self._events if event[0] <= target and event[1].state == "pending"]
        self._events = [event for event in self._events if event not in ready]
        for due, handle, callback, args, kwargs in sorted(ready, key=lambda event: event[0]):
            handle.state = "done"
            callback(*args, **kwargs)
