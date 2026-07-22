"""Read selected columns from CSV text."""

import csv
import io


class CsvProjectionError(ValueError):
    pass


class Column:
    def __init__(self, name, converter=str, required=True, default=None):
        self.name = name
        self.converter = converter
        self.required = required
        self.default = default


def read_projected_csv(text, columns, *, extra="reject"):
    rows = csv.DictReader(io.StringIO(text))
    result = []
    for row in rows:
        result.append({column.name: column.converter(row.get(column.name, column.default)) for column in columns})
    return result
