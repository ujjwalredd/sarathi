"""Permission inheritance policy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


class PermissionPolicyError(ValueError):
    """The permission policy is invalid."""


def resolve_permissions(
    node_id: str,
    nodes: Mapping[str, Mapping[str, object]],
    grants: Mapping[str, Mapping[str, Mapping[str, object]]],
    principal_ids: Iterable[str],
) -> frozenset[str]:
    allowed = set()
    node_grants = grants.get(node_id, {})
    for principal in principal_ids:
        record = node_grants.get(principal, {})
        allowed.update(record.get("allow", ()))
    return frozenset(allowed)
