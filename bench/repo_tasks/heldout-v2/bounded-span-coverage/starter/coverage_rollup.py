def aggregate_coverage(spans, *, max_spans, max_groups):
    totals = {}
    for resource, start, end in spans:
        if len(totals) > max_groups:
            raise OverflowError("too many resources")
        totals[resource] = totals.get(resource, 0) + (end - start)
    return tuple(totals.items())
