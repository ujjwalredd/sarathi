"""Cache results of idempotent operations."""


class IdempotencyCache:
    def __init__(self):
        self._values = {}

    def compute(self, key, function):
        value = self._values.get(key)
        if value:
            return value
        value = function()
        if value:
            self._values[key] = value
        return value

    def invalidate(self, key):
        return self._values.pop(key, None) is not None
