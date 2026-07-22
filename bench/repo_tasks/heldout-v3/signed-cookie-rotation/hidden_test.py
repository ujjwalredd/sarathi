import base64
import hashlib
import hmac
import unittest

from signed_cookies import CookieError, sign_cookie, verify_cookie


KEYS = {"current": b"current-test-key", "previous": b"previous-test-key"}


def make_token(value, key_id, issued_at, key):
    payload = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    message = f"v1.{key_id}.{issued_at}.{payload}"
    mac = hmac.new(key, message.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{message}.{mac}"


class SignedCookieTests(unittest.TestCase):
    def test_signing_is_exact_and_round_trips_unicode(self):
        token = sign_cookie("café ☕", KEYS["current"], key_id="current", issued_at=100)
        self.assertEqual(token, make_token("café ☕", "current", 100, KEYS["current"]))
        self.assertEqual(verify_cookie(token, KEYS, max_age=10, now=110), "café ☕")

    def test_previous_and_current_keys_are_selected_by_id(self):
        old = make_token("old", "previous", 95, KEYS["previous"])
        new = make_token("new", "current", 100, KEYS["current"])
        self.assertEqual(verify_cookie(old, KEYS, max_age=10, now=100), "old")
        self.assertEqual(verify_cookie(new, KEYS, max_age=0, now=100), "new")

    def test_age_boundaries_reject_expired_and_future_tokens(self):
        token = make_token("x", "current", 100, KEYS["current"])
        self.assertEqual(verify_cookie(token, KEYS, max_age=5, now=105), "x")
        with self.assertRaises(CookieError):
            verify_cookie(token, KEYS, max_age=4, now=105)
        with self.assertRaises(CookieError):
            verify_cookie(token, KEYS, max_age=5, now=99)

    def test_each_authenticated_field_and_signature_are_protected(self):
        token = make_token("x", "current", 100, KEYS["current"])
        variants = [
            token.replace(".current.", ".previous."),
            token.replace(".100.", ".101."),
            token[:-1] + ("0" if token[-1] != "0" else "1"),
        ]
        for candidate in variants:
            with self.subTest(candidate=candidate), self.assertRaises(CookieError):
                verify_cookie(candidate, KEYS, max_age=10, now=100)

    def test_noncanonical_base64_is_rejected_even_with_a_valid_mac(self):
        payload = "eA=="
        message = f"v1.current.100.{payload}"
        mac = hmac.new(KEYS["current"], message.encode("ascii"), hashlib.sha256).hexdigest()
        with self.assertRaises(CookieError):
            verify_cookie(f"{message}.{mac}", KEYS, max_age=1, now=100)

    def test_malformed_tokens_and_unknown_ids_use_cookie_error(self):
        candidates = ["", "v1.a.1.x", "v2.current.1.eA." + "0" * 64,
                      "v1.missing.1.eA." + "0" * 64, "v1.current.+1.eA." + "0" * 64]
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(CookieError):
                verify_cookie(candidate, KEYS, max_age=1, now=1)

    def test_verify_rejects_public_argument_type_and_range_errors(self):
        token = make_token("x", "current", 1, KEYS["current"])
        with self.assertRaises(TypeError):
            verify_cookie(123, KEYS, max_age=1, now=1)
        with self.assertRaises(TypeError):
            verify_cookie(token, KEYS, max_age=True, now=1)
        with self.assertRaises(ValueError):
            verify_cookie(token, KEYS, max_age=-1, now=1)
        with self.assertRaises(TypeError):
            verify_cookie(token, {"current": "not-bytes"}, max_age=1, now=1)

    def test_sign_rejects_invalid_inputs(self):
        bad_calls = [
            lambda: sign_cookie(3, b"k", key_id="kid", issued_at=1),
            lambda: sign_cookie("x", b"", key_id="kid", issued_at=1),
            lambda: sign_cookie("x", b"k", key_id="bad.id", issued_at=1),
            lambda: sign_cookie("x", b"k", key_id="kid", issued_at=True),
        ]
        for call in bad_calls:
            with self.subTest(call=call), self.assertRaises((TypeError, ValueError)):
                call()

    def test_key_mapping_is_not_mutated(self):
        keys = dict(KEYS)
        before = dict(keys)
        verify_cookie(make_token("x", "current", 1, KEYS["current"]), keys, max_age=0, now=1)
        self.assertEqual(keys, before)


unittest.main()
