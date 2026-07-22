"""Canonical HTTP URL helper."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class CanonicalUrlError(ValueError):
    pass


def canonicalize_url(url):
    parts = urlsplit(url)
    query = urlencode(sorted(parse_qsl(parts.query)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", query, ""))
