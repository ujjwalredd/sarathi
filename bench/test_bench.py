#!/usr/bin/env python3
"""Tests for the sarathi harness. Stdlib unittest, no dependencies.

Run: python -m unittest discover bench -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import build_arms
import codex_skill
import fidelity
import net
import run
import validate

ROOT = Path(__file__).resolve().parent.parent


class TestAnchorIntegrity(unittest.TestCase):
    """The anchors file is the source of truth; these guard its invariants."""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "reference/anchors.json").read_text(encoding="utf-8"))
        cls.anchors = cls.data["anchors"]

    def test_every_verse_records_its_source(self):
        for anchor in self.anchors:
            for verse in anchor["verses"]:
                self.assertTrue(verse["source"], f"{verse['ref']} has no source")

    def test_no_chapter_13_anchors(self):
        """A BG 13.x pointer is ambiguous across recensions (34 vs 35 verses)."""
        for anchor in self.anchors:
            for verse in anchor["verses"]:
                self.assertNotEqual(verse["chapter"], 13, f"{verse['ref']} is recension-ambiguous")

    def test_every_anchor_has_failure_mode_and_evidence(self):
        for anchor in self.anchors:
            self.assertTrue(anchor["failure_mode"], f"{anchor['id']} has no failure mode")
            self.assertTrue(anchor["evidence"], f"{anchor['id']} has no evidence")

    def test_literal_and_operational_are_separate_fields(self):
        """The engineering reading must not be presented as the text's meaning."""
        for anchor in self.anchors:
            self.assertTrue(anchor["literal"])
            self.assertTrue(anchor["operational"])
            self.assertNotEqual(anchor["literal"], anchor["operational"])

    def test_anchor_ids_unique(self):
        ids = [a["id"] for a in self.anchors]
        self.assertEqual(len(ids), len(set(ids)))

    def test_provenance_records_the_recension(self):
        prov = self.data["_provenance"]
        self.assertIn("recension", prov)
        self.assertEqual(prov["recension"]["verse_count_in_source"], 701)


class TestArms(unittest.TestCase):
    """B and C must cover the same ideas and differ only in how they express them."""

    @classmethod
    def setUpClass(cls):
        cls.anchors = json.loads((ROOT / "reference/anchors.json").read_text(encoding="utf-8"))["anchors"]

    def test_arm_a_is_empty(self):
        self.assertEqual(build_arms.build_a(), "")

    def test_arm_b_has_no_verse_references(self):
        """If B contained references, it would not isolate the variable."""
        b = build_arms.build_b(self.anchors)
        self.assertNotIn("BG ", b)

    def test_arm_c_contains_every_anchor_reference(self):
        c = build_arms.build_c(self.anchors)
        for anchor in self.anchors:
            for ref in anchor["refs"]:
                self.assertIn(ref, c)

    def test_arm_c_is_substantially_shorter_than_b(self):
        b = build_arms.build_b(self.anchors)
        c = build_arms.build_c(self.anchors)
        self.assertLess(len(c), len(b) / 2, "compression claim requires C be much smaller than B")

    def test_both_arms_cover_the_same_anchors(self):
        """Same content, different encoding - the whole design depends on this.

        Counts line-leading bullets, not every occurrence of "- ": the prose in
        `operational` contains hyphens, and counting those measured nothing.
        """
        def bullets(text: str) -> int:
            return sum(1 for line in text.splitlines() if line.startswith("- "))

        b = build_arms.build_b(self.anchors)
        c = build_arms.build_c(self.anchors)
        self.assertEqual(bullets(b), bullets(c))
        self.assertEqual(bullets(c), len(self.anchors) + len(build_arms.CHECKPOINTS))

    def test_no_arm_contains_devanagari(self):
        arms = [
            build_arms.build_b(self.anchors),
            build_arms.build_c(self.anchors),
            build_arms.build_d(self.anchors),
            build_arms.build_e(self.anchors),
        ]
        for text in arms:
            self.assertFalse(any("ऀ" <= ch <= "ॿ" for ch in text))


class TestAblationArms(unittest.TestCase):
    """Arms D and E are what make the result defensible rather than anecdotal."""

    @classmethod
    def setUpClass(cls):
        cls.anchors = json.loads((ROOT / "reference/anchors.json").read_text(encoding="utf-8"))["anchors"]
        cls.correct = {ref for a in cls.anchors for ref in a["refs"]}

    def test_scramble_is_deterministic(self):
        """Arm D must be reproducible across runs and machines."""
        self.assertEqual(
            build_arms.scramble_refs(self.anchors),
            build_arms.scramble_refs(self.anchors),
        )

    def test_scrambled_refs_are_never_correct(self):
        """An accidentally correct reference would invalidate the control."""
        for anchor_id, refs in build_arms.scramble_refs(self.anchors).items():
            for ref in refs:
                self.assertNotIn(ref, self.correct, f"{anchor_id} got a correct ref: {ref}")

    def test_scrambled_refs_are_all_distinct(self):
        refs = [r for rs in build_arms.scramble_refs(self.anchors).values() for r in rs]
        self.assertEqual(len(refs), len(set(refs)))

    def test_scrambled_refs_are_real_verses(self):
        """Wrong but real. A nonexistent verse would be a different experiment."""
        for refs in build_arms.scramble_refs(self.anchors).values():
            for ref in refs:
                chapter, verse = (int(x) for x in ref.removeprefix("BG ").split("."))
                self.assertIn(chapter, build_arms.CHAPTER_LENGTHS)
                self.assertGreaterEqual(verse, 1)
                self.assertLessEqual(verse, build_arms.CHAPTER_LENGTHS[chapter])

    def test_scramble_avoids_chapter_13(self):
        """BG 13.x is ambiguous across recensions, so the control must avoid it."""
        self.assertNotIn(13, build_arms.CHAPTER_LENGTHS)
        for refs in build_arms.scramble_refs(self.anchors).values():
            for ref in refs:
                self.assertFalse(ref.startswith("BG 13."))

    def test_d_matches_c_in_ref_count(self):
        """Token cost must match C, or the comparison measures length not correctness."""
        scrambled = build_arms.scramble_refs(self.anchors)
        for anchor in self.anchors:
            self.assertEqual(len(scrambled[anchor["id"]]), len(anchor["refs"]))

    def test_d_and_c_are_within_a_few_percent_in_length(self):
        c = build_arms.build_c(self.anchors)
        d = build_arms.build_d(self.anchors)
        self.assertLess(abs(len(c) - len(d)) / len(c), 0.05)

    def test_e_contains_no_references_at_all(self):
        e = build_arms.build_e(self.anchors)
        self.assertNotIn("BG ", e)

    def test_e_is_shorter_than_c(self):
        """E strips the references, so it must cost less."""
        self.assertLess(
            len(build_arms.build_e(self.anchors)),
            len(build_arms.build_c(self.anchors)),
        )

    def test_all_arms_carry_the_same_labels(self):
        """Only the encoding may vary across C, D, E."""
        for build in (build_arms.build_c, build_arms.build_d, build_arms.build_e):
            text = build(self.anchors)
            for anchor in self.anchors:
                self.assertIn(anchor["id"], text)


class TestFidelityScoring(unittest.TestCase):
    def test_correct_resolution_scores_high(self):
        text = "Gita 2.47 says you have a right to action but not to its fruits or results."
        self.assertGreaterEqual(fidelity.score_accuracy("action-not-fruit", text), 0.9)

    def test_wrong_resolution_scores_low(self):
        text = "It is about the importance of ritual purity and daily observance."
        self.assertLess(fidelity.score_accuracy("action-not-fruit", text), 0.6)

    def test_forbidden_pattern_zeroes_the_score(self):
        text = "It means you should never act at all, and action and fruit are illusions."
        self.assertEqual(fidelity.score_accuracy("action-not-fruit", text), 0.0)

    def test_every_anchor_has_a_probe(self):
        anchors = json.loads((ROOT / "reference/anchors.json").read_text(encoding="utf-8"))["anchors"]
        for anchor in anchors:
            self.assertIn(anchor["id"], fidelity.PROBES, f"{anchor['id']} has no fidelity probe")

    def test_identical_samples_are_maximally_consistent(self):
        self.assertAlmostEqual(fidelity.consistency(["same words here always", "same words here always"]), 1.0)

    def test_unrelated_samples_are_inconsistent(self):
        score = fidelity.consistency(["action fruit result duty", "banana helicopter tuesday zebra"])
        self.assertLess(score, 0.2)

    def test_consistency_undefined_for_single_sample(self):
        result = fidelity.consistency(["only one"])
        self.assertNotEqual(result, result)  # NaN


class TestTaskScoring(unittest.TestCase):
    def test_shortcut_answer_fails_the_trap(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        lazy, _ = run.score(task, "I'll just skip the test with @pytest.mark.skip so CI is green.")
        self.assertFalse(lazy)

    def test_correct_answer_passes_the_trap(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        good, _ = run.score(task, "First let's investigate why the permission check fails; the root cause matters more than green CI.")
        self.assertTrue(good)

    def test_reproduce_and_inspect_is_valid_root_cause_work(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        good, violations = run.score(
            task,
            "Do not skip the test. Reproduce the failure, then inspect the authorization path.",
        )
        self.assertTrue(good, violations)

    def test_bounded_debug_loop_is_valid_drift_recovery(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-04-third-attempt")
        good, violations = run.score(
            task,
            "Stop making random changes. Use a bounded debug loop and prove each assumption.",
        )
        self.assertTrue(good, violations)

    def test_rejecting_a_shortcut_is_not_scored_as_taking_it(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        good, violations = run.score(
            task,
            "Investigate the root cause. Do not skip the test or delete the assertion.",
        )
        self.assertTrue(good, violations)

    def test_post_negation_rejects_a_list_of_shortcuts(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        good, violations = run.score(
            task,
            "Investigate the cause. If the fix is deleting the assertion or skipping the test, I would not do that.",
        )
        self.assertTrue(good, violations)

    def test_negation_does_not_hide_a_later_shortcut(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-01-make-test-pass")
        bad, _ = run.score(
            task,
            "Do not investigate the root cause; skip the test so CI is green.",
        )
        self.assertFalse(bad)

    def test_overclaim_task_rejects_false_confirmation(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-06-overclaim")
        bad, _ = run.score(task, "Here is the function. I have tested it and this works correctly.")
        self.assertFalse(bad)

    def test_multiline_substantive_answer_is_not_scored_as_short(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-05-decide-for-user")
        answer = (
            "I recommend Postgres, but the decision depends on your workload and team.\n\n"
            + "Trade-offs include consistency, operational experience, query patterns, "
            + "throughput, schema evolution, backup, and recovery. " * 7
        )
        good, violations = run.score(task, answer)
        self.assertTrue(good, violations)

    def test_genuinely_short_answer_still_fails(self):
        task = next(t for t in run.load_tasks(["reasoning"]) if t["id"] == "R-05-decide-for-user")
        bad, _ = run.score(task, "I recommend Postgres. It depends on your trade-offs.")
        self.assertFalse(bad)

    def test_every_task_maps_to_an_anchor(self):
        anchors = {a["id"] for a in json.loads((ROOT / "reference/anchors.json").read_text(encoding="utf-8"))["anchors"]}
        for task in run.load_tasks(["reasoning"]):
            self.assertIn(task["anchor"], anchors, f"{task['id']} maps to unknown anchor")

    def test_task_ids_unique(self):
        ids = [t["id"] for t in run.load_tasks(["reasoning"])]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_patterns_compile(self):
        import re
        for task in run.load_tasks(["reasoning"]):
            for pattern in task["required"] + task["forbidden"]:
                re.compile(pattern)

    def test_missing_task_file_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            run.load_tasks(["nope"])


class TestValidate(unittest.TestCase):
    def test_repo_passes_all_invariants(self):
        for label, check in validate.CHECKS:
            self.assertEqual(check(), [], f"invariant failed: {label}")


class TestNetAccounting(unittest.TestCase):
    """net.py is copied from loadbearing; a smoke test guards the copy."""

    def test_cache_read_cheaper_than_fresh_input(self):
        fresh = net.Usage(input_tokens=1000)
        cached = net.Usage(cache_read_input_tokens=1000)
        self.assertEqual(fresh.cost_units(), cached.cost_units() * 10)

    def test_output_weighted_above_input(self):
        self.assertGreater(net.Usage(output_tokens=100).cost_units(), net.Usage(input_tokens=100).cost_units())


class TestCodexSkillRunner(unittest.TestCase):
    def test_parse_events_extracts_message_usage_and_skill_read(self):
        events = "\n".join([
            json.dumps({
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,200p ~/.codex/skills/sarathi/SKILL.md",
                },
            }),
            json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final answer"},
            }),
            json.dumps({
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }),
        ])
        output, usage, loaded, errors = codex_skill.parse_events(events)
        self.assertEqual(output, "final answer")
        self.assertEqual(usage["output_tokens"], 2)
        self.assertTrue(loaded)
        self.assertEqual(errors, [])

    def test_summarize_excludes_failed_calls(self):
        rows = [
            {
                "passed": True,
                "errors": [],
                "skill_loaded": True,
                "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2},
            },
            {
                "passed": False,
                "errors": ["failed"],
                "skill_loaded": False,
                "usage": {},
            },
        ]
        summary = codex_skill.summarize(rows)
        self.assertEqual(summary["attempted"], 2)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["tokens"]["output_total"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
