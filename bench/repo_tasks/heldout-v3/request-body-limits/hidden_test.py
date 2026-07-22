import unittest

from body_limits import BodyLimitError, BodyReadError, read_request_body


class RecordingStream:
    def __init__(self, data, per_call=None):
        self.data = data
        self.offset = 0
        self.calls = []
        self.per_call = per_call

    def read(self, size):
        self.calls.append(size)
        actual = size if self.per_call is None else min(size, self.per_call)
        chunk = self.data[self.offset:self.offset + actual]
        self.offset += len(chunk)
        return chunk


class OversizedChunkStream:
    def read(self, size):
        return b"x" * (size + 1)


class BodyLimitTests(unittest.TestCase):
    def test_declared_body_is_read_exactly_without_touching_following_bytes(self):
        stream = RecordingStream(b"bodyNEXT", per_call=2)
        result = read_request_body(stream, content_length="4", max_bytes=10, chunk_size=3)
        self.assertEqual(result, b"body")
        self.assertEqual(stream.offset, 4)
        self.assertEqual(stream.calls, [3, 2])

    def test_declared_zero_reads_nothing(self):
        stream = RecordingStream(b"next-request")
        self.assertEqual(read_request_body(stream, content_length="0", max_bytes=0), b"")
        self.assertEqual(stream.calls, [])

    def test_declared_limit_is_rejected_before_reading(self):
        stream = RecordingStream(b"anything")
        with self.assertRaises(BodyLimitError):
            read_request_body(stream, content_length="6", max_bytes=5)
        self.assertEqual(stream.calls, [])

    def test_short_reads_are_collected_and_premature_eof_is_rejected(self):
        stream = RecordingStream(b"abc", per_call=1)
        self.assertEqual(read_request_body(stream, content_length="3", max_bytes=3,
                                           chunk_size=2), b"abc")
        self.assertEqual(stream.calls, [2, 2, 1])
        with self.assertRaises(BodyReadError):
            read_request_body(RecordingStream(b"ab"), content_length="3", max_bytes=3)

    def test_unknown_length_is_bounded_and_not_truncated(self):
        exact = RecordingStream(b"abc")
        self.assertEqual(read_request_body(exact, content_length=None, max_bytes=3,
                                           chunk_size=2), b"abc")
        self.assertTrue(all(0 < size <= 2 for size in exact.calls))
        oversized = RecordingStream(b"abcd")
        with self.assertRaises(BodyLimitError):
            read_request_body(oversized, content_length=None, max_bytes=3, chunk_size=2)
        self.assertLessEqual(oversized.offset, 4)

    def test_zero_limit_without_length_uses_one_byte_to_detect_data(self):
        empty = RecordingStream(b"")
        self.assertEqual(read_request_body(empty, content_length=None, max_bytes=0), b"")
        self.assertEqual(empty.calls, [1])
        nonempty = RecordingStream(b"x")
        with self.assertRaises(BodyLimitError):
            read_request_body(nonempty, content_length=None, max_bytes=0)
        self.assertEqual(nonempty.calls, [1])

    def test_content_length_syntax_is_canonical(self):
        for value in ("", "+1", "01", "-1", " 1", "1 ", "1, 1", 1):
            stream = RecordingStream(b"x")
            with self.subTest(value=value), self.assertRaises((TypeError, BodyReadError)):
                read_request_body(stream, content_length=value, max_bytes=1)
            self.assertEqual(stream.calls, [])

    def test_stream_results_must_obey_the_read_contract(self):
        with self.assertRaises(BodyReadError):
            read_request_body(OversizedChunkStream(), content_length="1", max_bytes=1)
        with self.assertRaises(BodyReadError):
            read_request_body(RecordingStream("text"), content_length="1", max_bytes=1)
        with self.assertRaises(TypeError):
            read_request_body(object(), content_length="0", max_bytes=0)

    def test_public_numeric_arguments_are_strict(self):
        for kwargs, error in (
            ({"max_bytes": True, "chunk_size": 1}, TypeError),
            ({"max_bytes": -1, "chunk_size": 1}, ValueError),
            ({"max_bytes": 1, "chunk_size": False}, TypeError),
            ({"max_bytes": 1, "chunk_size": 0}, ValueError),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                read_request_body(RecordingStream(b""), content_length="0", **kwargs)


unittest.main()
