"""Small in-memory lease registry."""


class LeaseRegistry:
    def __init__(self, clock_ns):
        self._clock_ns = clock_ns
        self._leases = {}

    def acquire(self, key, owner, ttl_ns):
        if ttl_ns <= 0:
            raise ValueError("ttl_ns must be positive")
        now = self._clock_ns()
        current = self._leases.get(key)
        if current is not None and now <= current[1]:
            return False
        self._leases[key] = (owner, now + ttl_ns)
        return True

    def renew(self, key, owner, ttl_ns):
        if ttl_ns <= 0:
            raise ValueError("ttl_ns must be positive")
        now = self._clock_ns()
        current = self._leases.get(key)
        if current is None or current[0] != owner:
            return False
        self._leases[key] = (owner, now + ttl_ns)
        return True

    def release(self, key, owner):
        current = self._leases.get(key)
        if current is None or current[0] != owner:
            return False
        del self._leases[key]
        return True

    def holder(self, key):
        current = self._leases.get(key)
        return None if current is None else current[0]
