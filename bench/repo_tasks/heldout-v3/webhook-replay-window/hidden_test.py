import hashlib
import hmac
import unittest

from webhook_replay import ReplayError, WebhookError, verify_and_record


SECRET = b"webhook-test-key"


def signature(body, timestamp, secret=SECRET):
    digest = hmac.new(secret, timestamp.encode("ascii") + b"." + body,
                      hashlib.sha256).hexdigest()
    return "v1=" + digest


class WebhookReplayTests(unittest.TestCase):
    def test_valid_request_is_recorded_with_exact_expiry(self):
        seen = {}
        sig = signature(b"payload", "100")
        self.assertTrue(verify_and_record(b"payload", "100", sig, SECRET,
                                         now=103, tolerance=5, seen=seen))
        self.assertEqual(seen, {sig[3:]: 105})

    def test_same_authenticated_request_is_rejected_as_replay(self):
        sig = signature(b"payload", "100")
        seen = {sig[3:]: 105}
        before = dict(seen)
        with self.assertRaises(ReplayError):
            verify_and_record(b"payload", "100", sig, SECRET, now=104, tolerance=5, seen=seen)
        self.assertEqual(seen, before)

    def test_time_window_is_symmetric_and_inclusive(self):
        old_sig = signature(b"old", "95")
        future_sig = signature(b"future", "105")
        self.assertTrue(verify_and_record(b"old", "95", old_sig, SECRET,
                                         now=100, tolerance=5, seen={}))
        self.assertTrue(verify_and_record(b"future", "105", future_sig, SECRET,
                                         now=100, tolerance=5, seen={}))
        with self.assertRaises(WebhookError):
            verify_and_record(b"old", "94", signature(b"old", "94"), SECRET,
                              now=100, tolerance=5, seen={})
        with self.assertRaises(WebhookError):
            verify_and_record(b"future", "106", signature(b"future", "106"), SECRET,
                              now=100, tolerance=5, seen={})

    def test_body_timestamp_and_version_are_authenticated(self):
        sig = signature(b"right", "100")
        candidates = [(b"wrong", "100", sig), (b"right", "101", sig),
                      (b"right", "100", "v2=" + sig[3:])]
        for body, timestamp, candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(WebhookError):
                verify_and_record(body, timestamp, candidate, SECRET,
                                  now=100, tolerance=5, seen={})

    def test_bad_requests_never_change_replay_state(self):
        expired_key = "a" * 64
        for candidate in ("v1=" + "0" * 64, "v1=" + "A" * 64, "bad"):
            seen = {expired_key: 1}
            with self.subTest(candidate=candidate), self.assertRaises(WebhookError):
                verify_and_record(b"payload", "100", candidate, SECRET,
                                  now=100, tolerance=5, seen=seen)
            self.assertEqual(seen, {expired_key: 1})

    def test_expired_entries_are_removed_only_after_authentication(self):
        sig = signature(b"new", "100")
        seen = {"a" * 64: 99, "b" * 64: 100, "c" * 64: 101}
        verify_and_record(b"new", "100", sig, SECRET, now=100, tolerance=5, seen=seen)
        self.assertNotIn("a" * 64, seen)
        self.assertIn("b" * 64, seen)
        self.assertIn("c" * 64, seen)
        self.assertEqual(seen[sig[3:]], 105)

    def test_timestamp_and_signature_syntax_are_canonical(self):
        for timestamp in ("", "+1", "01", "-1", " 1", "1 "):
            with self.subTest(timestamp=timestamp), self.assertRaises(WebhookError):
                verify_and_record(b"x", timestamp, "v1=" + "0" * 64, SECRET,
                                  now=1, tolerance=1, seen={})
        valid = signature(b"x", "1")
        with self.assertRaises(WebhookError):
            verify_and_record(b"x", "1", valid.upper(), SECRET,
                              now=1, tolerance=1, seen={})

    def test_public_argument_validation(self):
        sig = signature(b"x", "1")
        calls = [
            (lambda: verify_and_record(bytearray(b"x"), "1", sig, SECRET,
                                       now=1, tolerance=1, seen={}), TypeError),
            (lambda: verify_and_record(b"x", "1", sig, b"", now=1,
                                       tolerance=1, seen={}), ValueError),
            (lambda: verify_and_record(b"x", "1", sig, SECRET, now=True,
                                       tolerance=1, seen={}), TypeError),
            (lambda: verify_and_record(b"x", "1", sig, SECRET, now=1,
                                       tolerance=-1, seen={}), ValueError),
            (lambda: verify_and_record(b"x", "1", sig, SECRET, now=1,
                                       tolerance=1, seen=[]), TypeError),
        ]
        for call, error in calls:
            with self.subTest(call=call), self.assertRaises(error):
                call()

    def test_invalid_existing_state_is_rejected_without_mutation(self):
        sig = signature(b"x", "1")
        bad_states = [{"bad": 2}, {"a" * 64: True}, {"a" * 64: -1}]
        for seen in bad_states:
            before = dict(seen)
            with self.subTest(seen=seen), self.assertRaises((TypeError, ValueError)):
                verify_and_record(b"x", "1", sig, SECRET, now=1, tolerance=1, seen=seen)
            self.assertEqual(seen, before)


unittest.main()
