import unittest

from mapping_transaction import MappingTransaction


class MappingTransactionTests(unittest.TestCase):
    def test_commit_keeps_visible_changes(self):
        mapping = {"a": 1}
        transaction = MappingTransaction(mapping)
        transaction.set("a", 2)
        transaction.set("b", 3)
        self.assertEqual(mapping, {"a": 2, "b": 3})
        transaction.commit()
        self.assertEqual(mapping, {"a": 2, "b": 3})
        with self.assertRaises(RuntimeError):
            transaction.set("c", 4)

    def test_context_exception_restores_repeated_mutations(self):
        original_a = object()
        mapping = {"a": original_a, "b": 2}
        with self.assertRaises(ValueError):
            with MappingTransaction(mapping) as transaction:
                transaction.set("a", "temporary")
                transaction.delete("a")
                transaction.set("a", "final")
                transaction.delete("b")
                transaction.set("new", 9)
                raise ValueError("abort")
        self.assertEqual(set(mapping), {"a", "b"})
        self.assertIs(mapping["a"], original_a)
        self.assertEqual(mapping["b"], 2)

    def test_missing_delete_does_not_poison_rollback(self):
        mapping = {}
        transaction = MappingTransaction(mapping)
        with self.assertRaises(KeyError):
            transaction.delete("missing")
        transaction.set("present", 1)
        transaction.rollback()
        self.assertEqual(mapping, {})

    def test_rollback_to_savepoint_with_repeated_keys(self):
        mapping = {"item": "original"}
        transaction = MappingTransaction(mapping)
        transaction.set("before", 1)
        savepoint = transaction.savepoint()
        transaction.set("item", "second")
        transaction.set("item", "third")
        transaction.delete("item")
        transaction.set("created", object())
        transaction.rollback_to(savepoint)
        self.assertEqual(mapping, {"item": "original", "before": 1})
        transaction.set("after", 2)
        transaction.commit()
        self.assertEqual(mapping, {"item": "original", "before": 1, "after": 2})

    def test_later_savepoints_invalidated(self):
        mapping = {}
        transaction = MappingTransaction(mapping)
        first = transaction.savepoint()
        second = transaction.savepoint()
        transaction.set("x", 1)
        transaction.rollback_to(first)
        with self.assertRaises(ValueError):
            transaction.rollback_to(second)
        transaction.set("y", 2)
        transaction.rollback_to(first)
        self.assertEqual(mapping, {})
        transaction.commit()

    def test_foreign_savepoints_rejected(self):
        first = MappingTransaction({})
        second = MappingTransaction({})
        first_token = first.savepoint()
        second_token = second.savepoint()
        with self.assertRaises(ValueError):
            first.rollback_to(second_token)
        with self.assertRaises(ValueError):
            second.rollback_to(first_token)
        with self.assertRaises(ValueError):
            first.rollback_to(object())
        first.rollback()
        second.rollback()

    def test_rollback_closes_all_operations(self):
        mapping = {"a": 1}
        transaction = MappingTransaction(mapping)
        token = transaction.savepoint()
        transaction.set("a", 2)
        transaction.rollback()
        self.assertEqual(mapping, {"a": 1})
        operations = [
            lambda: transaction.set("x", 1), lambda: transaction.delete("a"),
            transaction.savepoint, lambda: transaction.rollback_to(token),
            transaction.commit, transaction.rollback, transaction.__enter__,
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(RuntimeError):
                operation()

    def test_base_exception_rolls_back(self):
        class StopNow(BaseException):
            pass

        mapping = {"stable": True}
        with self.assertRaises(StopNow):
            with MappingTransaction(mapping) as transaction:
                transaction.set("stable", False)
                transaction.set("temporary", True)
                raise StopNow()
        self.assertEqual(mapping, {"stable": True})


if __name__ == "__main__":
    unittest.main()
