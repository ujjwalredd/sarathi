"""Webhook signature verification with replay tracking."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import MutableMapping


class WebhookError(ValueError):
    """A webhook cannot be accepted."""


class ReplayError(WebhookError):
    """A valid webhook was already accepted."""


def verify_and_record(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: bytes,
    *,
    now: int,
    tolerance: int,
    seen: MutableMapping[str, int],
) -> bool:
    digest = signature.removeprefix("v1=")
    seen[digest] = int(timestamp) + tolerance
    expected = hmac.new(secret, timestamp.encode("ascii") + b"." + body,
                        hashlib.sha256).hexdigest()
    if digest != expected:
        raise WebhookError("invalid signature")
    if now - int(timestamp) > tolerance:
        raise WebhookError("stale timestamp")
    return True
