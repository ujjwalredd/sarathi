"""Shared retry budget."""


class RetryBudget:
    def __init__(self, capacity, initial_tokens=None):
        self.capacity = capacity
        self.tokens = capacity if initial_tokens is None else initial_tokens

    @property
    def available(self):
        return self.tokens

    def try_consume(self):
        if self.tokens == 0:
            return False
        self.tokens -= 1
        return True

    def replenish(self, amount=1):
        self.tokens = min(self.capacity, self.tokens + amount)
        return self.tokens


def retry(operation, *, budget, max_attempts, retryable=(Exception,),
          backoff_ns=None, sleep_ns=None):
    for attempt in range(max_attempts):
        try:
            return operation()
        except retryable:
            if not budget.try_consume():
                return None
            if sleep_ns is not None:
                delay = 0 if backoff_ns is None else backoff_ns(attempt)
                sleep_ns(delay)
    return None
