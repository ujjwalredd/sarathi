import copy
import hashlib
import hmac
import json
import math
import unittest

from audit_chain import AuditChainError, append_event, verify_chain


KEY = b"audit-chain-test-key"


def expected_mac(seq, prev, event, key=KEY):
    payload = json.dumps({"seq": seq, "prev": prev, "event": event}, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


class AuditChainTests(unittest.TestCase):
    def test_append_uses_exact_canonical_authenticated_format(self):
        chain = []
        event = {"message": "café", "ok": True, "details": {"b": 2, "a": 1}}
        entry = append_event(chain, event, key=KEY)
        expected = {"seq": 0, "prev": "0" * 64, "event": event,
                    "mac": expected_mac(0, "0" * 64, event)}
        self.assertEqual(entry, expected)
        self.assertEqual(chain, [expected])
        self.assertTrue(verify_chain(chain, key=KEY))

    def test_multiple_entries_link_to_authenticated_predecessor(self):
        chain = []
        first = append_event(chain, {"action": "create"}, key=KEY)
        second = append_event(chain, {"action": "update"}, key=KEY)
        self.assertEqual(second["seq"], 1)
        self.assertEqual(second["prev"], first["mac"])
        self.assertEqual(second["mac"], expected_mac(1, first["mac"], {"action": "update"}))
        self.assertTrue(verify_chain(chain, key=KEY))

    def test_event_key_order_does_not_change_mac(self):
        left = []
        right = []
        append_event(left, {"a": 1, "b": 2}, key=KEY)
        append_event(right, {"b": 2, "a": 1}, key=KEY)
        self.assertEqual(left[0]["mac"], right[0]["mac"])

    def test_event_tampering_sequence_tampering_and_link_tampering_fail(self):
        chain = []
        append_event(chain, {"n": 1}, key=KEY)
        append_event(chain, {"n": 2}, key=KEY)
        variants = []
        for change in ("event", "seq", "prev"):
            candidate = copy.deepcopy(chain)
            if change == "event":
                candidate[0]["event"]["n"] = 9
            elif change == "seq":
                candidate[1]["seq"] = 5
            else:
                candidate[1]["prev"] = "f" * 64
            variants.append(candidate)
        for candidate in variants:
            with self.subTest(candidate=candidate), self.assertRaises(AuditChainError):
                verify_chain(candidate, key=KEY)

    def test_wrong_key_and_mac_syntax_fail(self):
        chain = []
        append_event(chain, {"n": 1}, key=KEY)
        with self.assertRaises(AuditChainError):
            verify_chain(chain, key=b"different-test-key")
        changed = copy.deepcopy(chain)
        changed[0]["mac"] = changed[0]["mac"].upper()
        with self.assertRaises(AuditChainError):
            verify_chain(changed, key=KEY)

    def test_entry_and_event_schemas_are_exact(self):
        chain = []
        append_event(chain, {"n": 1}, key=KEY)
        bad_entry = copy.deepcopy(chain)
        bad_entry[0]["extra"] = 1
        with self.assertRaises(AuditChainError):
            verify_chain(bad_entry, key=KEY)
        for event in ([], {1: "bad"}, {"bad": (1, 2)}, {"bad": b"bytes"}, {"bad": math.nan}):
            with self.subTest(event=event), self.assertRaises((TypeError, AuditChainError)):
                append_event([], event, key=KEY)

    def test_source_event_is_detached(self):
        event = {"nested": [{"value": 1}]}
        chain = []
        append_event(chain, event, key=KEY)
        event["nested"][0]["value"] = 2
        self.assertEqual(chain[0]["event"], {"nested": [{"value": 1}]})
        self.assertTrue(verify_chain(chain, key=KEY))

    def test_failed_append_is_atomic(self):
        chain = []
        append_event(chain, {"ok": 1}, key=KEY)
        chain[0]["event"]["ok"] = 2
        before = copy.deepcopy(chain)
        with self.assertRaises(AuditChainError):
            append_event(chain, {"next": 1}, key=KEY)
        self.assertEqual(chain, before)
        with self.assertRaises(AuditChainError):
            append_event(chain, {"bad": object()}, key=KEY)
        self.assertEqual(chain, before)

    def test_public_container_and_key_types_are_strict(self):
        with self.assertRaises(TypeError):
            verify_chain("not-a-sequence-of-entries", key=KEY)
        with self.assertRaises(TypeError):
            verify_chain([], key=bytearray(KEY))
        with self.assertRaises(ValueError):
            verify_chain([], key=b"")
        with self.assertRaises(TypeError):
            append_event((), {"ok": 1}, key=KEY)


unittest.main()
