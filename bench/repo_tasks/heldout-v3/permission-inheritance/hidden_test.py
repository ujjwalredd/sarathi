import copy
import unittest

from permissions import PermissionPolicyError, resolve_permissions


def base_policy():
    nodes = {
        "root": {"parent": None, "inherits": True},
        "team": {"parent": "root", "inherits": True},
        "doc": {"parent": "team", "inherits": True},
    }
    grants = {
        "root": {"everyone": {"allow": ["read", "share"], "deny": []}},
        "team": {"staff": {"allow": ["write"], "deny": ["share"]}},
        "doc": {"alice": {"allow": ["delete", "share"], "deny": []}},
    }
    return nodes, grants


class PermissionInheritanceTests(unittest.TestCase):
    def test_inherits_for_all_principals_and_deny_wins(self):
        nodes, grants = base_policy()
        result = resolve_permissions("doc", nodes, grants, ["alice", "staff", "everyone"])
        self.assertEqual(result, frozenset({"read", "write", "delete"}))
        self.assertIsInstance(result, frozenset)

    def test_break_node_is_included_but_stops_ancestors(self):
        nodes, grants = base_policy()
        nodes["team"]["inherits"] = False
        result = resolve_permissions("doc", nodes, grants, ["alice", "staff", "everyone"])
        self.assertEqual(result, frozenset({"write", "delete"}))

    def test_denies_override_allows_at_any_level(self):
        nodes, grants = base_policy()
        grants["root"]["everyone"]["deny"] = ["delete"]
        grants["doc"]["alice"]["deny"] = ["read"]
        result = resolve_permissions("doc", nodes, grants, ["alice", "everyone"])
        self.assertEqual(result, frozenset({"share"}))

    def test_missing_target_parent_and_cycles_are_rejected(self):
        nodes, grants = base_policy()
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("missing", nodes, grants, [])
        broken = copy.deepcopy(nodes)
        broken["team"]["parent"] = "missing"
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", broken, grants, [])
        cyclic = copy.deepcopy(nodes)
        cyclic["root"]["parent"] = "doc"
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", cyclic, grants, [])

    def test_complete_hierarchy_is_validated_not_just_target_chain(self):
        nodes, grants = base_policy()
        nodes["bad-a"] = {"parent": "bad-b", "inherits": True}
        nodes["bad-b"] = {"parent": "bad-a", "inherits": True}
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, grants, ["alice"])

    def test_node_and_grant_schemas_are_exact(self):
        nodes, grants = base_policy()
        bad_nodes = copy.deepcopy(nodes)
        bad_nodes["doc"]["extra"] = 1
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", bad_nodes, grants, [])
        bad_grants = copy.deepcopy(grants)
        bad_grants["doc"]["alice"] = {"allow": ["read"]}
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, bad_grants, ["alice"])
        unknown_node = copy.deepcopy(grants)
        unknown_node["missing"] = {}
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, unknown_node, [])

    def test_permission_and_principal_types_are_strict(self):
        nodes, grants = base_policy()
        grants["doc"]["alice"]["allow"] = "read"
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, grants, ["alice"])
        nodes, grants = base_policy()
        grants["doc"]["alice"]["deny"] = ["execute"]
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, grants, ["alice"])
        with self.assertRaises(TypeError):
            resolve_permissions("doc", nodes, grants, "alice")
        with self.assertRaises(PermissionPolicyError):
            resolve_permissions("doc", nodes, grants, [""])

    def test_inputs_are_not_mutated(self):
        nodes, grants = base_policy()
        before_nodes = copy.deepcopy(nodes)
        before_grants = copy.deepcopy(grants)
        principals = ["alice", "everyone"]
        resolve_permissions("doc", nodes, grants, principals)
        self.assertEqual(nodes, before_nodes)
        self.assertEqual(grants, before_grants)
        self.assertEqual(principals, ["alice", "everyone"])


unittest.main()
