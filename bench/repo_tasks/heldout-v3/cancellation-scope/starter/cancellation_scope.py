"""Hierarchical cancellation scopes."""

import threading


class Cancelled(RuntimeError):
    pass


class CancellationScope:
    def __init__(self, parent=None):
        self.parent = parent
        self._cancelled = False
        self._event = threading.Event()

    def child(self):
        return CancellationScope(self)

    def cancel(self):
        if self._cancelled:
            return False
        self._cancelled = True
        self._event.set()
        return True

    @property
    def is_cancelled(self):
        return self._cancelled or (self.parent is not None and self.parent.is_cancelled)

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    def checkpoint(self):
        if self.is_cancelled:
            raise Cancelled("scope was cancelled")
