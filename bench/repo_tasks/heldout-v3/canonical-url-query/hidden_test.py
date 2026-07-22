import unittest

from canonical_url import CanonicalUrlError, canonicalize_url


class CanonicalUrlTests(unittest.TestCase):
    def test_authority_defaults_idna_and_fragment(self):
        self.assertEqual(canonicalize_url("HTTP://BÜCHER.Example.:80#top"), "http://xn--bcher-kva.example/")
        self.assertEqual(canonicalize_url("https://Example.COM:443/a"), "https://example.com/a")
        self.assertEqual(canonicalize_url("https://Example.COM:444/a"), "https://example.com:444/a")

    def test_path_segments_slashes_and_percent_normalization(self):
        url = "https://EXAMPLE.com/a//b/./c/../%7euser/%2f/%2e%2e/"
        self.assertEqual(canonicalize_url(url), "https://example.com/a//b/~user/%2F/../")
        self.assertEqual(canonicalize_url("http://x/../../a/.."), "http://x/")

    def test_unicode_path_and_encoded_slash(self):
        self.assertEqual(canonicalize_url("https://x.test/café/%2f"), "https://x.test/caf%C3%A9/%2F")
        self.assertEqual(canonicalize_url("https://x.test/a%2Fb"), "https://x.test/a%2Fb")

    def test_query_filter_duplicates_blanks_and_sorting(self):
        url = "https://x.test?p=2&utm_Source=gone&empty&b=hello+world&p=1&a=%7E&FBCLID=x"
        self.assertEqual(canonicalize_url(url), "https://x.test/?a=~&b=hello%20world&empty=&p=1&p=2")

    def test_query_uses_decoded_sort_order_and_strict_utf8(self):
        self.assertEqual(canonicalize_url("http://x/?z=%C3%A9&%C3%A4=2&a=3"), "http://x/?a=3&z=%C3%A9&%C3%A4=2")
        with self.assertRaises(CanonicalUrlError):
            canonicalize_url("http://x/?a=%FF")

    def test_ipv6_and_invalid_authorities(self):
        self.assertEqual(canonicalize_url("http://[2001:DB8::1]:80/a"), "http://[2001:db8::1]/a")
        for url in ("ftp://x/a", "/relative", "http://user:pw@x/", "http://x:bad/", "http:///a"):
            with self.subTest(url=url):
                with self.assertRaises(CanonicalUrlError):
                    canonicalize_url(url)

    def test_rejects_types_space_controls_and_bad_escapes(self):
        for url in (None, b"http://x", "http://x/a b", "http://x/a\nb", "http://x/%", "http://x/%GG", "http://%GG/", "http://x/?a=%1"):
            with self.subTest(url=url):
                with self.assertRaises((TypeError, CanonicalUrlError)):
                    canonicalize_url(url)


if __name__ == "__main__":
    unittest.main()
