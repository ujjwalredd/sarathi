import unittest

from cleanup_scope import CleanupError, CleanupScope


class CleanupScopeTests(unittest.TestCase):
    def test_lifo_arguments_and_idempotent_close(self):
        observed = []
        scope = CleanupScope()
        scope.defer(observed.append, "first")
        scope.defer(lambda prefix, *, suffix: observed.append(prefix + suffix), "sec", suffix="ond")
        self.assertTrue(scope.close())
        self.assertFalse(scope.close())
        self.assertEqual(observed, ["second", "first"])

    def test_cancel_identity_and_idempotence(self):
        observed = []
        scope = CleanupScope()
        keep = scope.defer(observed.append, "keep")
        discard = scope.defer(observed.append, "discard")
        self.assertTrue(scope.cancel(discard))
        self.assertFalse(scope.cancel(discard))
        self.assertFalse(scope.cancel(object()))
        self.assertTrue(scope.close())
        self.assertEqual(observed, ["keep"])
        self.assertIsNotNone(keep)

    def test_collects_failures_in_execution_order(self):
        observed = []

        def fail(label):
            observed.append(label)
            raise ValueError(label)

        scope = CleanupScope()
        scope.defer(fail, "first")
        scope.defer(observed.append, "middle")
        scope.defer(fail, "last")
        with self.assertRaises(CleanupError) as caught:
            scope.close()
        self.assertEqual(observed, ["last", "middle", "first"])
        self.assertEqual([str(error) for error in caught.exception.errors], ["last", "first"])
        self.assertIsNone(caught.exception.primary)
        self.assertFalse(scope.close())

    def test_normal_context_exit(self):
        observed = []
        with CleanupScope() as scope:
            scope.defer(observed.append, 1)
            scope.defer(observed.append, 2)
        self.assertEqual(observed, [2, 1])
        self.assertFalse(scope.close())

    def test_body_exception_propagates_unchanged(self):
        observed = []
        body_error = ValueError("body")
        try:
            with CleanupScope() as scope:
                scope.defer(observed.append, "cleaned")
                raise body_error
        except ValueError as caught:
            self.assertIs(caught, body_error)
        else:
            self.fail("body exception was suppressed")
        self.assertEqual(observed, ["cleaned"])

    def test_body_and_cleanup_failures_preserved(self):
        body_error = KeyError("body")

        def fail(label):
            raise RuntimeError(label)

        with self.assertRaises(CleanupError) as caught:
            with CleanupScope() as scope:
                scope.defer(fail, "earlier")
                scope.defer(fail, "later")
                raise body_error
        failure = caught.exception
        self.assertIs(failure.primary, body_error)
        self.assertIs(failure.__cause__, body_error)
        self.assertEqual([str(error) for error in failure.errors], ["later", "earlier"])

    def test_closed_before_callbacks(self):
        results = []
        scope = CleanupScope()
        token = scope.defer(lambda: results.append(scope.close()))
        self.assertTrue(scope.close())
        self.assertEqual(results, [False])
        with self.assertRaises(RuntimeError):
            scope.defer(lambda: None)
        with self.assertRaises(RuntimeError):
            scope.cancel(token)
        with self.assertRaises(RuntimeError):
            scope.__enter__()


if __name__ == "__main__":
    unittest.main()
