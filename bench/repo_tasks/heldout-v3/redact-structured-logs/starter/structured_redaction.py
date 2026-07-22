"""Redact secret values in structured log records."""


DEFAULT_SENSITIVE_KEYS = {"password", "token", "secret"}


class RedactionError(ValueError):
    pass


def redact_record(record, *, sensitive_keys=DEFAULT_SENSITIVE_KEYS, replacement="[REDACTED]", max_depth=32):
    if isinstance(record, dict):
        for key, value in record.items():
            if key.lower() in sensitive_keys:
                record[key] = replacement
            else:
                record[key] = redact_record(value, sensitive_keys=sensitive_keys, replacement=replacement, max_depth=max_depth)
    elif isinstance(record, list):
        for index, value in enumerate(record):
            record[index] = redact_record(value, sensitive_keys=sensitive_keys, replacement=replacement, max_depth=max_depth)
    return record
