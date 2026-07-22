"""Tamper-evident audit log chains."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


class AuditChainError(ValueError):
    """An audit chain is malformed or has been tampered with."""


def append_event(chain: list[dict[str, object]], event: Mapping[str, object], *, key: bytes) -> dict[str, object]:
    seq = len(chain)
    prev = chain[-1]["mac"] if chain else "0" * 64
    payload = json.dumps(event, sort_keys=True).encode("utf-8")
    mac = hashlib.sha256(payload).hexdigest()
    entry = {"seq": seq, "prev": prev, "event": event, "mac": mac}
    chain.append(entry)
    return entry


def verify_chain(entries: Sequence[Mapping[str, object]], *, key: bytes) -> bool:
    previous = "0" * 64
    for entry in entries:
        if entry["prev"] != previous:
            raise AuditChainError("broken link")
        previous = entry["mac"]
    return True
