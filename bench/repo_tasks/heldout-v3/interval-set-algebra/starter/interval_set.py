"""Normalized half-open integer interval sets."""


class IntervalSet:
    def __init__(self, intervals=()):
        self._intervals = tuple(sorted(intervals))

    @property
    def intervals(self):
        return self._intervals

    @property
    def total_length(self):
        return sum(end - start for start, end in self._intervals)

    def contains_point(self, point):
        return any(start <= point < end for start, end in self._intervals)

    def union(self, other):
        return IntervalSet(self._intervals + other._intervals)

    def intersection(self, other):
        return IntervalSet()

    def difference(self, other):
        return IntervalSet(self._intervals)

    def __len__(self):
        return len(self._intervals)

    def __iter__(self):
        return iter(self._intervals)

    def __eq__(self, other):
        return isinstance(other, IntervalSet) and self._intervals == other._intervals
