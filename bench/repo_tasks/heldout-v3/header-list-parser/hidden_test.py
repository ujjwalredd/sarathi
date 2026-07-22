import unittest

from header_lists import HeaderListError, parse_header_list


class HeaderListTests(unittest.TestCase):
    def test_tokens_and_optional_whitespace(self):
        self.assertEqual(parse_header_list("gzip, br,custom_token"),
                         ["gzip", "br", "custom_token"])
        self.assertEqual(parse_header_list("\talpha \t,\tbeta\t"), ["alpha", "beta"])

    def test_quoted_commas_empty_value_and_escapes(self):
        value = '"a,b", "", "quote: \\" and slash: \\\\"'
        self.assertEqual(parse_header_list(value), ["a,b", "", 'quote: " and slash: \\'])

    def test_token_punctuation_is_exact(self):
        valid = "!#$%&'*+-.^_`|~AZaz09"
        self.assertEqual(parse_header_list(valid), [valid])
        for value in ("has space", "semi;colon", "name=value", "café"):
            with self.subTest(value=value), self.assertRaises(HeaderListError):
                parse_header_list(value)

    def test_empty_elements_and_trailing_commas_are_errors(self):
        for value in ("", "   ", ",a", "a,,b", "a,", "a, \t"):
            with self.subTest(value=value), self.assertRaises(HeaderListError):
                parse_header_list(value)

    def test_quoted_string_must_be_well_formed_and_consume_the_item(self):
        bad = ['"unterminated', '"ok"junk', '"bad\\q"', '"line\nfeed"', '"control\x1f"']
        for value in bad:
            with self.subTest(value=value), self.assertRaises(HeaderListError):
                parse_header_list(value)

    def test_limits_reject_instead_of_truncating(self):
        self.assertEqual(parse_header_list("a,bb", max_items=2, max_item_length=2), ["a", "bb"])
        with self.assertRaises(HeaderListError):
            parse_header_list("a,b,c", max_items=2)
        with self.assertRaises(HeaderListError):
            parse_header_list('"abc"', max_item_length=2)

    def test_limits_use_decoded_length(self):
        self.assertEqual(parse_header_list('"a\\\\b"', max_item_length=3), ["a\\b"])
        with self.assertRaises(HeaderListError):
            parse_header_list('"a\\\\b"', max_item_length=2)

    def test_public_argument_validation(self):
        for call, error in (
            (lambda: parse_header_list(b"a"), TypeError),
            (lambda: parse_header_list("a", max_items=True), TypeError),
            (lambda: parse_header_list("a", max_item_length=1.5), TypeError),
            (lambda: parse_header_list("a", max_items=0), ValueError),
            (lambda: parse_header_list("a", max_item_length=-1), ValueError),
        ):
            with self.subTest(call=call), self.assertRaises(error):
                call()


unittest.main()
