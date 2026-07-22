"""A basic token bucket."""


class TokenBucket:
    def __init__(self, capacity, refill_rate_per_ns, clock_ns):
        self.capacity = capacity
        self.refill_rate_per_ns = refill_rate_per_ns
        self.clock_ns = clock_ns
        self.tokens = capacity
        self.last_refill = clock_ns()

    def _refill(self):
        now = self.clock_ns()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + int(elapsed * self.refill_rate_per_ns))
        self.last_refill = now

    def try_acquire(self, amount=1):
        self._refill()
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True

    @property
    def available(self):
        return self.tokens
