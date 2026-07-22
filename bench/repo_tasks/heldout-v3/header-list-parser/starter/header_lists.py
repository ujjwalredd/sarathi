"""Parsers for bounded HTTP list fields."""

from __future__ import annotations


class HeaderListError(ValueError):
    """A list field does not match the supported grammar."""


def parse_header_list(value: str, *, max_items: int = 32, max_item_length: int = 256) -> list[str]:
    items = []
    for raw in value.split(","):
        item = raw.strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if item:
            items.append(item)
    return items[:max_items]
