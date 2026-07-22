import unittest

from csv_projection import Column, CsvProjectionError, read_projected_csv


class CsvProjectionTests(unittest.TestCase):
    def test_projection_conversion_order_and_quoted_fields(self):
        columns = [Column("name"), Column("age", int), Column("note")]
        got = read_projected_csv('name,age,note\n"Doe, Jane",37,"line 1\nline 2"\n', columns)
        self.assertEqual(got, [{"name": "Doe, Jane", "age": 37, "note": "line 1\nline 2"}])
        self.assertEqual(tuple(got[0]), ("name", "age", "note"))

    def test_missing_optional_and_default_not_converted(self):
        columns = [Column("id", int), Column("country", lambda value: value.upper(), default="us"), Column("memo", required=False)]
        got = read_projected_csv("id\n4\n", columns)
        self.assertEqual(got, [{"id": 4, "country": "us", "memo": None}])

    def test_empty_present_value_is_converted(self):
        seen = []
        columns = [Column("value", lambda value: seen.append(value) or "converted")]
        self.assertEqual(read_projected_csv('value\n""\n', columns), [{"value": "converted"}])
        self.assertEqual(seen, [""])

    def test_extra_policy_and_missing_required(self):
        with self.assertRaises(CsvProjectionError) as extra:
            read_projected_csv("a,b\n1,2\n", [Column("a")])
        self.assertIsNone(extra.exception.row_number)
        self.assertEqual(read_projected_csv("a,b\n1,2\n", [Column("a")], extra="ignore"), [{"a": "1"}])
        with self.assertRaises(CsvProjectionError) as missing:
            read_projected_csv("a\n1\n", [Column("b")], extra="ignore")
        self.assertEqual(missing.exception.column, "b")

    def test_duplicate_header_schema_and_empty_input(self):
        with self.assertRaises(CsvProjectionError):
            read_projected_csv("a,a\n1,2\n", [Column("a")])
        with self.assertRaises(CsvProjectionError):
            read_projected_csv("a\n1\n", [Column("a"), Column("a")])
        with self.assertRaises(CsvProjectionError):
            read_projected_csv("", [Column("a")])

    def test_row_shape_strict_csv_and_atomic_conversion(self):
        with self.assertRaises(CsvProjectionError) as shape:
            read_projected_csv("a,b\n1\n", [Column("a"), Column("b")])
        self.assertEqual(shape.exception.row_number, 2)
        with self.assertRaises(CsvProjectionError):
            read_projected_csv('a\n"unterminated\n', [Column("a")])
        calls = []
        def convert(value):
            calls.append(value)
            if value == "bad": raise RuntimeError("boom")
            return value
        with self.assertRaises(CsvProjectionError) as converted:
            read_projected_csv("a\nok\nbad\nafter\n", [Column("a", convert)])
        self.assertEqual(converted.exception.row_number, 3)
        self.assertEqual(converted.exception.column, "a")
        self.assertIsInstance(converted.exception.__cause__, RuntimeError)
        self.assertEqual(calls, ["ok", "bad"])

    def test_argument_validation_and_generator_schema(self):
        schema = (item for item in [Column("a")])
        self.assertEqual(read_projected_csv("a\nx\n", schema), [{"a": "x"}])
        for call in (
            lambda: read_projected_csv(b"a\n", []),
            lambda: read_projected_csv("a\n", "a"),
            lambda: read_projected_csv("a\n", [object()]),
            lambda: read_projected_csv("a\n", [], extra="drop"),
            lambda: Column("", str),
            lambda: Column("a", 1),
            lambda: Column("a", str, required=1),
        ):
            with self.subTest(call=call):
                with self.assertRaises((TypeError, ValueError, CsvProjectionError)):
                    call()


if __name__ == "__main__":
    unittest.main()
