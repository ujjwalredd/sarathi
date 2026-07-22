"""Bounded request body reads."""

from __future__ import annotations


class BodyReadError(ValueError):
    """A request body cannot be read according to its framing."""


class BodyLimitError(BodyReadError):
    """A request body exceeds the configured limit."""


def read_request_body(
    stream: object,
    *,
    content_length: str | None,
    max_bytes: int,
    chunk_size: int = 8192,
) -> bytes:
    data = stream.read()
    if content_length is not None and len(data) < int(content_length):
        raise BodyReadError("premature EOF")
    return data[:max_bytes]
