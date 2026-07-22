"""Ordered mapping helper."""


def ordered_map(function, iterable, max_workers):
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    results = []
    for item in iterable:
        results.append(function(item))
    return results
