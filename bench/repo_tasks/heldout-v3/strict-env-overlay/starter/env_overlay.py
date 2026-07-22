"""Apply a small environment overlay language."""


class EnvOverlayError(ValueError):
    pass


def apply_env_overlay(base, lines):
    """Return *base* with simple NAME=VALUE lines applied."""
    result = dict(base)
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            result.pop(line[1:], None)
            continue
        name, value = line.split("=", 1)
        result[name] = value
    return result
