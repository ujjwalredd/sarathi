"""Versioned signed cookies."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping


class CookieError(ValueError):
    """The cookie is invalid or cannot be trusted."""


def sign_cookie(value: str, key: bytes, *, key_id: str, issued_at: int) -> str:
    payload = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    message = f"v1.{key_id}.{issued_at}.{payload}"
    signature = hmac.new(key, message.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{message}.{signature}"


def verify_cookie(
    token: str, keys: Mapping[str, bytes], *, max_age: int, now: int
) -> str:
    try:
        version, key_id, issued_text, payload, signature = token.split(".")
        issued_at = int(issued_text)
        key = keys[key_id]
    except (ValueError, KeyError) as exc:
        raise CookieError("malformed cookie") from exc
    if version != "v1":
        raise CookieError("unsupported cookie version")
    message = f"{version}.{key_id}.{issued_text}.{payload}"
    expected = hmac.new(key, message.encode("ascii"), hashlib.sha256).hexdigest()
    if signature != expected:
        raise CookieError("bad signature")
    if now - issued_at > max_age:
        raise CookieError("expired cookie")
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding).decode("utf-8")
