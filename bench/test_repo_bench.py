from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import repo_bench


class RepoBenchmarkTests(unittest.TestCase):
    def test_heldout_task_ids_are_frozen(self):
        self.assertEqual(
            {task.task_id for task in repo_bench.load_tasks("heldout-v2")},
            {
                "bounded-span-coverage",
                "canonical-json-payload",
                "cleanup-scope-failure-preservation",
                "mapping-transaction-savepoints",
                "revisioned-state-waiters",
                "strict-content-type-parser",
                "virtual-time-stable-scheduler",
                "workspace-state-migration",
            },
        )

    def test_heldout_tasks_are_complete_and_bounded(self):
        tasks = repo_bench.load_tasks("heldout-v2")
        self.assertEqual(len(tasks), 8)
        self.assertEqual(len({task.task_id for task in tasks}), len(tasks))
        for task in tasks:
            self.assertTrue(task.prompt)
            self.assertTrue(repo_bench.tree_manifest(task.starter))
            compile(task.hidden_test.read_text(encoding="utf-8"), str(task.hidden_test), "exec")

    def test_exact_task_selection_and_unknown_id(self):
        tasks = repo_bench.load_tasks("heldout-v2", ["bounded-span-coverage"])
        self.assertEqual([task.task_id for task in tasks], ["bounded-span-coverage"])
        with self.assertRaisesRegex(ValueError, "unknown task ids"):
            repo_bench.load_tasks("heldout-v2", ["missing-task"])

    def test_prompt_has_action_request_and_exact_arm(self):
        task = repo_bench.load_tasks("heldout-v2", ["bounded-span-coverage"])[0]
        prompt = repo_bench.build_prompt(task, "ARM GUIDANCE\n")
        self.assertTrue(prompt.startswith("ARM GUIDANCE\n\n"))
        self.assertIn("Implement the request in the files", prompt)
        self.assertIn(task.prompt, prompt)

    def test_codex_parser_requires_message_and_usage(self):
        stream = "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}),
            ]
        )
        message, usage, errors = repo_bench.parse_codex_jsonl(stream)
        self.assertEqual(message, "done")
        self.assertEqual(usage["input_tokens"], 10)
        self.assertEqual(errors, [])

        _, _, errors = repo_bench.parse_codex_jsonl("not-json")
        self.assertIn("missing final agent message", errors)
        self.assertIn("missing token usage", errors)

    def test_skipped_hidden_tests_are_detected(self):
        self.assertEqual(repo_bench.skipped_test_count("OK (skipped=7)"), 7)
        self.assertEqual(repo_bench.skipped_test_count("OK"), 0)

    def test_visible_prompt_text_preserves_lines_for_leak_checks(self):
        payload = [{"content": [{"text": "Available skills\n- sarathi: leaked"}]}]
        rendered = repo_bench.visible_prompt_text(payload)
        self.assertRegex(rendered, r"(?m)^- sarathi:")

    def test_tree_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.py"
            target.write_text("pass\n", encoding="utf-8")
            link = root / "link.py"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(ValueError, "symlink"):
                repo_bench.regular_files(root)

    def test_generated_cache_cleanup_is_narrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "module.pyc").write_bytes(b"cache")
            source = root / "module.py"
            source.write_text("pass\n", encoding="utf-8")
            extra_test = root / "test_module.py"
            extra_test.write_text("pass\n", encoding="utf-8")

            repo_bench.remove_generated_artifacts(root)

            self.assertFalse(cache.exists())
            self.assertTrue(source.exists())
            self.assertTrue(extra_test.exists())

    def test_grader_scratch_cleanup_does_not_touch_solution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scratch = root / ".grader-tmp"
            scratch.mkdir()
            (scratch / "temporary").write_text("x", encoding="utf-8")
            source = root / "solution.py"
            source.write_text("pass\n", encoding="utf-8")

            repo_bench.remove_grader_scratch(root)

            self.assertFalse(scratch.exists())
            self.assertTrue(source.exists())

    def test_dry_run_makes_no_model_call(self):
        with mock.patch.object(repo_bench.shutil, "which", return_value="/usr/bin/codex"):
            with mock.patch.object(repo_bench.subprocess, "run") as run:
                self.assertEqual(
                    repo_bench.main(["--dry-run", "--task-ids", "bounded-span-coverage"]),
                    0,
                )
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
