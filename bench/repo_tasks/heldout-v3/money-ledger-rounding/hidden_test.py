from decimal import Decimal
import unittest

from money_ledger import LedgerError, MoneyLedger, UnbalancedTransaction


class MoneyLedgerTests(unittest.TestCase):
    def test_half_even_rounding_balanced_post_and_types(self):
        ledger = MoneyLedger(2)
        transaction = ledger.post([("cash", "1.005"), ("revenue", Decimal("-1.004"))])
        self.assertEqual(transaction, (("cash", Decimal("1.00")), ("revenue", Decimal("-1.00"))))
        self.assertTrue(all(isinstance(amount, Decimal) for account, amount in transaction))
        self.assertEqual(ledger.balance("cash"), Decimal("1.00"))
        huge = 10 ** 60
        large = MoneyLedger(2)
        large.post([("asset", huge), ("equity", -huge)])
        self.assertEqual(large.balance("asset"), Decimal(str(huge) + ".00"))

    def test_independent_rounding_can_make_transaction_unbalanced(self):
        ledger = MoneyLedger(2)
        with self.assertRaises(UnbalancedTransaction) as caught:
            ledger.post([("a", "1.005"), ("b", "-1.006")])
        self.assertEqual(caught.exception.difference, Decimal("-0.01"))
        self.assertEqual(ledger.balances(), {})
        self.assertEqual(ledger.journal, ())

    def test_duplicate_accounts_order_and_caller_independence(self):
        entries = [["b", "2"], ["a", "-1"], ["b", "-1"]]
        ledger = MoneyLedger()
        posted = ledger.post(entries)
        entries[0][0] = "changed"
        self.assertEqual(posted, (("b", Decimal("2.00")), ("a", Decimal("-1.00")), ("b", Decimal("-1.00"))))
        self.assertEqual(ledger.balances(), {"b": Decimal("1.00"), "a": Decimal("-1.00")})
        self.assertEqual(tuple(ledger.balances()), ("b", "a"))

    def test_failure_after_valid_entry_is_atomic(self):
        ledger = MoneyLedger()
        ledger.post([("cash", "3"), ("equity", "-3")])
        before_balances, before_journal = ledger.balances(), ledger.journal
        def entries():
            yield "new", "1"
            yield "bad\naccount", "-1"
        with self.assertRaises((TypeError, ValueError, LedgerError)):
            ledger.post(entries())
        self.assertEqual(ledger.balances(), before_balances)
        self.assertEqual(ledger.journal, before_journal)

    def test_reverse_restores_balances_and_records_exact_lines(self):
        ledger = MoneyLedger()
        original = ledger.post([("cash", "5.00"), ("fee", "-0.25"), ("income", "-4.75")])
        reversal = ledger.reverse(0)
        self.assertEqual(reversal, tuple((account, -amount) for account, amount in original))
        self.assertEqual(ledger.balances(), {"cash": Decimal("0.00"), "fee": Decimal("0.00"), "income": Decimal("0.00")})
        self.assertEqual(len(ledger.journal), 2)
        before = ledger.journal
        with self.assertRaises(IndexError):
            ledger.reverse(-1)
        self.assertEqual(ledger.journal, before)

    def test_rejects_amount_shortcuts_and_invalid_transactions(self):
        invalid_amounts = [1.25, True, " 1.00", "NaN", "Infinity", "", object()]
        for amount in invalid_amounts:
            with self.subTest(amount=amount):
                ledger = MoneyLedger()
                with self.assertRaises((TypeError, ValueError, LedgerError)):
                    ledger.post([("a", amount), ("b", 0)])
                self.assertEqual(ledger.journal, ())
        for entries in ([], [("a", 0), ("b", 0)], [("a", 1)], "a,1"):
            with self.subTest(entries=entries):
                with self.assertRaises((TypeError, ValueError, LedgerError, UnbalancedTransaction)):
                    MoneyLedger().post(entries)

    def test_scale_account_and_index_validation(self):
        for scale in (-1, 10, True, 1.5):
            with self.subTest(scale=scale):
                with self.assertRaises((TypeError, ValueError)):
                    MoneyLedger(scale)
        ledger = MoneyLedger(0)
        self.assertEqual(ledger.balance("unseen"), Decimal("0"))
        for account in ("", "bad\x00name", 2):
            with self.subTest(account=account):
                with self.assertRaises((TypeError, ValueError)):
                    ledger.balance(account)
        with self.assertRaises(TypeError):
            ledger.reverse(True)


if __name__ == "__main__":
    unittest.main()
