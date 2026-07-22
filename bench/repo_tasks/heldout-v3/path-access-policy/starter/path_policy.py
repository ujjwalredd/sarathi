"""Path access policy helpers."""

from __future__ import annotations

import os
from pathlib import Path


class PathAccessError(ValueError):
    """A requested path is outside the configured policy."""


def resolve_allowed_path(root: str | os.PathLike[str], requested: str) -> Path:
    root_path = Path(root).resolve()
    candidate = (root_path / requested).resolve()
    if not str(candidate).startswith(str(root_path)):
        raise PathAccessError("path escapes root")
    return candidate
