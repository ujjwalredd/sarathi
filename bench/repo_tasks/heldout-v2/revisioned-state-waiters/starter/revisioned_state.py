import time


class VersionedState:
    def __init__(self, initial):
        self._value = initial
        self._revision = 0

    def snapshot(self):
        return self._revision, self._value

    def write(self, value):
        if value != self._value:
            self._value = value
            self._revision += 1
        return self._revision

    def compare_and_set(self, expected_revision, value):
        if self._revision != expected_revision:
            return False, self._revision
        return True, self.write(value)

    def wait_after(self, revision, timeout=None):
        deadline = None if timeout is None else time.time() + timeout
        while self._revision <= revision:
            if deadline is not None and time.time() >= deadline:
                return None
            time.sleep(0.01)
        return self.snapshot()
