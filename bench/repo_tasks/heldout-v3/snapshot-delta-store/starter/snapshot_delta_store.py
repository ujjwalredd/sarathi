"""Versioned snapshot and delta store."""

from dataclasses import dataclass


DELETE = object()


class Conflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    version: int
    data: dict


@dataclass(frozen=True)
class Delta:
    version: int
    changes: dict


class SnapshotDeltaStore:
    def __init__(self, initial=None):
        self._data = dict(initial or {})
        self._version = 0
        self._deltas = []

    def snapshot(self):
        return Snapshot(self._version, self._data)

    def apply(self, changes, expected_version):
        if expected_version != self._version:
            raise Conflict("stale version")
        for key, value in changes.items():
            if value is DELETE:
                self._data.pop(key, None)
            else:
                self._data[key] = value
        self._version += 1
        self._deltas.append(Delta(self._version, dict(changes)))
        return self._version

    def deltas_since(self, version):
        return tuple(delta for delta in self._deltas if delta.version > version)
