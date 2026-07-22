"""Circuit breaker with a caller-provided clock."""


class CircuitOpen(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold, recovery_timeout_ns, clock_ns):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_ns = recovery_timeout_ns
        self.clock_ns = clock_ns
        self.failures = 0
        self.opened_at = None
        self._state = "closed"

    @property
    def state(self):
        return self._state

    def call(self, function):
        now = self.clock_ns()
        if self._state == "open":
            if now - self.opened_at <= self.recovery_timeout_ns:
                raise CircuitOpen("circuit is open")
            self._state = "half_open"
        try:
            result = function()
        except Exception:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self._state = "open"
                self.opened_at = now
            return None
        self.failures = 0
        self._state = "closed"
        return result
