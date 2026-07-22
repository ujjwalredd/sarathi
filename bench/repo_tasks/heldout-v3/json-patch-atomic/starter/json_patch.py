"""Apply JSON patch-like operations."""

import copy


class PatchError(ValueError):
    pass


def apply_patch(document, operations):
    result = copy.deepcopy(document)
    for operation in operations:
        path = operation["path"].strip("/")
        target = result
        parts = path.split("/") if path else []
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        key = parts[-1] if parts else None
        if operation["op"] in ("add", "replace"):
            if key is None:
                result = operation["value"]
            elif isinstance(target, list):
                target[int(key)] = operation["value"]
            else:
                target[key] = operation["value"]
        elif operation["op"] == "remove":
            if isinstance(target, list):
                del target[int(key)]
            else:
                del target[key]
    return result
