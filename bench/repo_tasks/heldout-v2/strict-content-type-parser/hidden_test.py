import unittest

from content_type import parse_content_type


class ParseContentTypeTests(unittest.TestCase):
    def test_normalizes_type_and_sorts_parameters(self):
        self.assertEqual(
            parse_content_type(' Text / HTML ; Charset = "utf-8" ; boundary=AbC '),
            ("text", "html", (("boundary", "AbC"), ("charset", "utf-8"))),
        )

    def test_accepts_ows_and_empty_quoted_value(self):
        self.assertEqual(
            parse_content_type('\tapplication/json\t;\tprofile\t=\t""\t'),
            ("application", "json", (("profile", ""),)),
        )

    def test_decodes_only_supported_quoted_escapes(self):
        value = r'Application/X-Test; note="a; b\\c\"d"; flag=YES'
        self.assertEqual(
            parse_content_type(value),
            ("application", "x-test", (("flag", "YES"), ("note", 'a; b\\c"d'))),
        )

    def test_rejects_duplicate_parameters(self):
        with self.assertRaises(ValueError):
            parse_content_type("text/plain; Charset=utf-8; CHARSET=ascii")

    def test_rejects_missing_or_extra_grammar(self):
        invalid = [
            "", "text", "/plain", "text/", "text/plain;", "text/plain;;x=y",
            "text/plain;x", "text/plain x=y", "text/plain;x=y junk",
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_content_type(value)

    def test_rejects_bad_tokens_quotes_and_escapes(self):
        invalid = [
            "te()xt/plain", "text/pl@in", "text/plain;bad name=x",
            "text/plain;x=hello/world", 'text/plain;x="unterminated',
            r'text/plain;x="bad\q"', 'text/plain;x="raw"quote"',
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_content_type(value)

    def test_rejects_non_ascii_and_controls(self):
        invalid = [
            "text/plain;title=café", "text/plain\r\nx:y", 'text/plain;x="a\tb"',
            "text/\x7fplain", "text/plain;\x00x=y",
        ]
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                parse_content_type(value)

    def test_rejects_non_string_input(self):
        for value in (None, b"text/plain", 12):
            with self.subTest(value=value), self.assertRaises(TypeError):
                parse_content_type(value)


if __name__ == "__main__":
    unittest.main()
