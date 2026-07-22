"""Structured secret redaction."""

from __future__ import annotations

from collections.abc import Iterable


DEFAULT_SENSITIVE_KEYS = ("password", "token", "secret", "api_key")


def redact_secrets(
    value: object,
    *,
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
    replacement: str = "[REDACTED]",
) -> object:
    names = {name.lower() for name in sensitive_keys}
    if isinstance(value, dict):
        for key in value:
            if key.lower() in names:
                value[key] = replacement
        return value
    return value
