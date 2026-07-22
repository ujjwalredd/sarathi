"""Configuration schema migration."""

from __future__ import annotations

from collections.abc import Mapping


class ConfigError(ValueError):
    """Configuration data is invalid or unsupported."""


def migrate_config(config: Mapping[str, object]) -> dict[str, object]:
    version = config.get("version")
    if version == 3:
        return dict(config)
    if version == 2:
        return {
            "version": 3,
            "service": config["service"],
            "auth": {"scheme": "bearer", "token": config["token"]},
            "retry": {"max_attempts": config.get("max_retries", 3)},
        }
    return {
        "version": 3,
        "service": {"url": config["endpoint"],
                    "timeout_ms": config["timeout_seconds"]},
        "auth": {"scheme": "bearer", "token": config["api_key"]},
        "retry": {"max_attempts": 3},
    }
