"""A bounded cache."""


_MISSING = object()


class LRUCache:
    def __init__(self, capacity, on_evict=None):
        self.capacity = capacity
        self.on_evict = on_evict
        self.data = {}

    def put(self, key, value):
        self.data[key] = value
        if len(self.data) > self.capacity:
            del self.data[next(iter(self.data))]

    def get(self, key, default=_MISSING):
        if key in self.data:
            return self.data[key]
        if default is _MISSING:
            raise KeyError(key)
        return default

    def delete(self, key):
        return self.data.pop(key)

    def resize(self, capacity):
        self.capacity = capacity

    def clear(self):
        self.data.clear()

    def keys(self):
        return tuple(self.data)

    def __len__(self):
        return len(self.data)
