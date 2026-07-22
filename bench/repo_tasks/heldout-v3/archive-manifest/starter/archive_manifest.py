"""Validation for archive manifests."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class ManifestError(ValueError):
    """An archive manifest is unsafe or malformed."""


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    type: str
    size: int
    sha256: str | None


def validate_manifest(
    entries: Iterable[Mapping[str, object]], *, max_files: int, max_total_size: int
) -> tuple[ArchiveEntry, ...]:
    result = []
    total = 0
    for raw in entries:
        entry = ArchiveEntry(raw["path"], raw["type"], raw["size"], raw["sha256"])
        if entry.path.startswith("/") or ".." in entry.path:
            raise ManifestError("unsafe path")
        if entry.type == "file":
            total += entry.size
        result.append(entry)
    if len(result) > max_files or total > max_total_size:
        raise ManifestError("manifest limit exceeded")
    return tuple(result)
