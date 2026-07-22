"""A tiny in-memory money ledger."""


class LedgerError(ValueError):
    pass


class UnbalancedTransaction(LedgerError):
    pass


class MoneyLedger:
    def __init__(self, scale=2):
        self.scale = scale
        self._balances = {}
        self._journal = []

    def post(self, entries):
        normalized = tuple((account, round(float(amount), self.scale)) for account, amount in entries)
        for account, amount in normalized:
            self._balances[account] = self._balances.get(account, 0) + amount
        self._journal.append(normalized)
        return normalized

    def balance(self, account):
        return self._balances.get(account, 0)

    def balances(self):
        return dict(self._balances)

    @property
    def journal(self):
        return tuple(self._journal)

    def reverse(self, index):
        return self.post((account, -amount) for account, amount in self._journal[index])
