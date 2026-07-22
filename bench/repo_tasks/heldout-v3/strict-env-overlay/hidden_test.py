import unittest

from env_overlay import EnvOverlayError, apply_env_overlay


class EnvOverlayTests(unittest.TestCase):
    def test_ordered_expansion_removal_and_copy(self):
        base = {"ROOT": "/srv", "DROP": "x", "LITERAL": "$HOME"}
        got = apply_env_overlay(base, ["BIN=${ROOT}/bin", "ROOT=/opt", "COPY=${LITERAL}", "!DROP"])
        self.assertEqual(got, {"ROOT": "/opt", "BIN": "/srv/bin", "COPY": "$HOME", "LITERAL": "$HOME"})
        self.assertEqual(base, {"ROOT": "/srv", "DROP": "x", "LITERAL": "$HOME"})

    def test_comments_endings_and_significant_space(self):
        got = apply_env_overlay({}, ["  # ignored\r\n", "\t\n", "A= value \r\n", "B=$$${A}"])
        self.assertEqual(got["A"], " value ")
        self.assertEqual(got["B"], "$ value ")

    def test_invalid_lines_report_exact_index(self):
        bad = ["OK=yes", "NOPE", "AFTER=no"]
        with self.assertRaises(EnvOverlayError) as caught:
            apply_env_overlay({}, bad)
        self.assertEqual(caught.exception.line_number, 1)
        self.assertIn("assignment", caught.exception.reason.lower())

    def test_invalid_dollar_forms_and_undefined(self):
        for text in ("A=$", "A=$NAME", "A=${}", "A=${BAD-NAME}", "A=${MISSING}", "A=${OPEN"):
            with self.subTest(text=text):
                with self.assertRaises(EnvOverlayError):
                    apply_env_overlay({}, [text])

    def test_names_nul_and_embedded_newline(self):
        for text in (" BAD=x", "A =x", "9A=x", "!=x", "!", "A=x\x00y", "A=x\ny"):
            with self.subTest(text=text):
                with self.assertRaises(EnvOverlayError):
                    apply_env_overlay({}, [text])

    def test_input_types_and_base_validation(self):
        with self.assertRaises(TypeError):
            apply_env_overlay([], [])
        with self.assertRaises(TypeError):
            apply_env_overlay({"A": 1}, [])
        with self.assertRaises(TypeError):
            apply_env_overlay({}, "A=x")
        with self.assertRaises(TypeError):
            apply_env_overlay({}, [b"A=x"])
        with self.assertRaises(EnvOverlayError):
            apply_env_overlay({"BAD-NAME": "x"}, [])

    def test_generator_and_original_unchanged_on_late_error(self):
        base = {"A": "old"}
        lines = (line for line in ["A=new", "B=${A}", "BROKEN"])
        with self.assertRaises(EnvOverlayError):
            apply_env_overlay(base, lines)
        self.assertEqual(base, {"A": "old"})


if __name__ == "__main__":
    unittest.main()
