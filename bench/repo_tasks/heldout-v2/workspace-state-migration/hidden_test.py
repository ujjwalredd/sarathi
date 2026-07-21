import copy
import unittest

from state_migration import migrate_workspace_state


class WorkspaceStateMigrationTests(unittest.TestCase):
    def test_migrates_version_one(self):
        state = {"version": 1, "name": "Ada", "notify": True, "labels": ["beta", "alpha"]}
        self.assertEqual(migrate_workspace_state(state), {
            "version": 3, "profile": {"display_name": "Ada"}, "channels": ["email"],
            "labels": ["alpha", "beta"], "revision": 0,
        })

    def test_migrates_version_two(self):
        state = {
            "version": 2, "profile": {"display_name": "Grace"},
            "subscriptions": {"email": True, "sms": True},
            "labels": {"z": False, "alpha": True, "beta": True}, "revision": 7,
        }
        self.assertEqual(migrate_workspace_state(state), {
            "version": 3, "profile": {"display_name": "Grace"},
            "channels": ["email", "sms"], "labels": ["alpha", "beta"], "revision": 7,
        })

    def test_version_three_idempotent_and_rebuilt(self):
        state = {
            "version": 3, "profile": {"display_name": "Lin"},
            "channels": ["email", "sms"], "labels": ["alpha", "z"], "revision": 2,
        }
        result = migrate_workspace_state(state)
        self.assertEqual(result, state)
        self.assertIsNot(result, state)
        self.assertIsNot(result["profile"], state["profile"])
        self.assertIsNot(result["channels"], state["channels"])
        self.assertIsNot(result["labels"], state["labels"])
        self.assertEqual(migrate_workspace_state(result), result)

    def test_does_not_mutate_older_state(self):
        state = {
            "version": 2, "profile": {"display_name": "Noor"},
            "subscriptions": {"email": False, "sms": True},
            "labels": {"x": True}, "revision": 1,
        }
        snapshot = copy.deepcopy(state)
        migrate_workspace_state(state)
        self.assertEqual(state, snapshot)

    def test_rejects_schema_keys(self):
        invalid = [
            {"version": 1, "name": "A", "notify": False},
            {"version": 2, "profile": {"display_name": "A"}, "subscriptions": {"email": False, "sms": False}, "labels": {}, "revision": 0, "extra": None},
            {"version": 3, "profile": {"display_name": "A"}, "channels": [], "labels": []},
            {"version": 2, "profile": {"display_name": "A", "extra": True}, "subscriptions": {"email": False, "sms": False}, "labels": {}, "revision": 0},
        ]
        for state in invalid:
            with self.subTest(state=state), self.assertRaises(ValueError):
                migrate_workspace_state(state)

    def test_rejects_state_or_version(self):
        with self.assertRaises(TypeError):
            migrate_workspace_state([])
        with self.assertRaises(ValueError):
            migrate_workspace_state({})
        with self.assertRaises(TypeError):
            migrate_workspace_state({"version": True})
        with self.assertRaises(ValueError):
            migrate_workspace_state({"version": 4})

    def test_rejects_invalid_nested_values(self):
        invalid = [
            ({"version": 1, "name": "A", "notify": 1, "labels": []}, TypeError),
            ({"version": 1, "name": "A", "notify": False, "labels": ["x", "x"]}, ValueError),
            ({"version": 2, "profile": {"display_name": " padded "}, "subscriptions": {"email": False, "sms": False}, "labels": {}, "revision": 0}, ValueError),
            ({"version": 2, "profile": {"display_name": "A"}, "subscriptions": {"email": False, "sms": False}, "labels": {}, "revision": -1}, ValueError),
            ({"version": 2, "profile": {"display_name": "A"}, "subscriptions": {"email": False, "sms": False}, "labels": {"x": 1}, "revision": 0}, TypeError),
        ]
        for state, error in invalid:
            with self.subTest(state=state), self.assertRaises(error):
                migrate_workspace_state(state)

    def test_rejects_noncanonical_version_three(self):
        base = {"version": 3, "profile": {"display_name": "A"}, "channels": [], "labels": [], "revision": 0}
        invalid = []
        for channels in (["sms", "email"], ["email", "email"], ["push"]):
            state = copy.deepcopy(base)
            state["channels"] = channels
            invalid.append(state)
        for labels in (["z", "a"], ["a", "a"], ["Bad"]):
            state = copy.deepcopy(base)
            state["labels"] = labels
            invalid.append(state)
        for state in invalid:
            with self.subTest(state=state), self.assertRaises(ValueError):
                migrate_workspace_state(state)


if __name__ == "__main__":
    unittest.main()
