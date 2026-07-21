#!/usr/bin/env python3
"""Benchmark the installed Sarathi skill in isolated Codex sessions.

Run the baseline before installing the skill, install it, then run the treatment:

    python bench/codex_skill.py --condition baseline --expect-skill absent --n 3
    python bench/codex_skill.py --condition sarathi --expect-skill present --n 3
    python bench/codex_skill.py --condition sarathi-explicit --expect-skill present --n 3

Each task runs in a fresh, ephemeral Codex session rooted at an empty temporary
directory. That prevents the agent from discovering this repository and learning
that the prompt is a benchmark fixture. No arm text is injected: the treatment is
the globally installed skill, discovered through Codex's normal routing.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

import run

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL = Path.home() / ".codex" / "skills" / "sarathi" / "SKILL.md"
SCENARIO_PREAMBLE = (
    "Treat the following as a hypothetical engineering decision scenario. "
    "No project files are available. Do not inspect a workspace or run tools; "
    "state the response and actions you would take.\n\n"
)
EXPLICIT_SKILL_PREAMBLE = "Use the sarathi skill for this scenario.\n\n"


def skill_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_events(stdout: str) -> tuple[str, dict, bool, list[str]]:
    """Extract the final response, usage, and evidence that SKILL.md was read."""
    messages: list[str] = []
    usage: dict = {}
    skill_loaded = False
    errors: list[str] = []

    for lineno, line in enumerate(stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"stdout line {lineno} was not JSON")
            continue

        if "sarathi" in line.lower() and "skill.md" in line.lower():
            skill_loaded = True

        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                messages.append(item.get("text", ""))
        elif event.get("type") == "turn.completed":
            usage = event.get("usage", {})

    return (messages[-1] if messages else "", usage, skill_loaded, errors)


def run_one(prompt: str, model: str, effort: str, timeout: int, workspace: Path) -> dict:
    cmd = [
        "codex", "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--model", model,
        "--config", f'model_reasoning_effort="{effort}"',
        "--cd", str(workspace),
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "output": "",
            "usage": {},
            "skill_loaded": False,
            "errors": [f"timeout after {timeout}s"],
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }

    output, usage, loaded, errors = parse_events(proc.stdout)
    if proc.returncode:
        errors.append(f"codex exited {proc.returncode}")
    return {
        "output": output,
        "usage": usage,
        "skill_loaded": loaded,
        "errors": errors,
        "stderr": proc.stderr[-2000:],
    }


def summarize(rows: list[dict]) -> dict:
    valid = [row for row in rows if not row["errors"]]
    passed = sum(row["passed"] for row in valid)
    usage_rows = [row["usage"] for row in valid if row["usage"]]

    def total(field: str) -> int:
        return sum(int(usage.get(field, 0) or 0) for usage in usage_rows)

    def mean(field: str) -> float:
        values = [int(usage.get(field, 0) or 0) for usage in usage_rows]
        return statistics.fmean(values) if values else 0.0

    return {
        "attempted": len(rows),
        "valid": len(valid),
        "errors": len(rows) - len(valid),
        "passed": passed,
        "pass_rate": passed / len(valid) if valid else None,
        "skill_loaded_calls": sum(row["skill_loaded"] for row in valid),
        "tokens": {
            "input_total": total("input_tokens"),
            "cached_input_total": total("cached_input_tokens"),
            "output_total": total("output_tokens"),
            "reasoning_output_total": total("reasoning_output_tokens"),
            "input_mean": mean("input_tokens"),
            "cached_input_mean": mean("cached_input_tokens"),
            "output_mean": mean("output_tokens"),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark an installed skill in isolated Codex sessions.")
    parser.add_argument(
        "--condition",
        required=True,
        choices=["baseline", "sarathi", "sarathi-explicit"],
    )
    parser.add_argument("--expect-skill", required=True, choices=["absent", "present"])
    parser.add_argument("--skill-path", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--tasks", nargs="+", default=["reasoning"])
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "codex-skill")
    args = parser.parse_args(argv)

    if not shutil.which("codex"):
        parser.error("`codex` is not on PATH")
    if args.n < 1 or args.jobs < 1:
        parser.error("--n and --jobs must be positive")

    digest = skill_digest(args.skill_path)
    present = digest is not None
    if present != (args.expect_skill == "present"):
        state = "present" if present else "absent"
        parser.error(f"expected skill to be {args.expect_skill}, but it is {state}: {args.skill_path}")

    tasks = run.load_tasks(args.tasks)
    jobs = [
        (rep, task)
        for rep in range(args.n)
        for task in tasks
    ]
    print(f"{args.condition}: {len(tasks)} tasks x {args.n} reps = {len(jobs)} Codex calls")

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sarathi-codex-bench-") as tmp:
        workspace = Path(tmp)

        def execute(job: tuple[int, dict]) -> dict:
            rep, task = job
            invocation = EXPLICIT_SKILL_PREAMBLE if args.condition == "sarathi-explicit" else ""
            result = run_one(
                invocation + SCENARIO_PREAMBLE + task["prompt"],
                args.model,
                args.effort,
                args.timeout,
                workspace,
            )
            passed, violations = run.score(task, result["output"])
            return {
                "task_id": task["id"],
                "anchor": task["anchor"],
                "rep": rep,
                "passed": passed,
                "violations": violations,
                **result,
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(execute, job): job for job in jobs}
            for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                row = future.result()
                rows.append(row)
                status = "ERROR" if row["errors"] else ("pass" if row["passed"] else "FAIL")
                print(f"[{index:>2}/{len(jobs)}] rep{row['rep'] + 1} {row['task_id']:<24} {status}")

    rows.sort(key=lambda row: (row["rep"], row["task_id"]))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    artifact = {
        "metadata": {
            "timestamp": stamp,
            "condition": args.condition,
            "model": args.model,
            "reasoning_effort": args.effort,
            "codex_version": subprocess.run(
                ["codex", "--version"], capture_output=True, text=True, check=False
            ).stdout.strip(),
            "skill_path": str(args.skill_path),
            "skill_sha256": digest,
            "skill_expected": args.expect_skill,
            "skill_invocation": {
                "baseline": "none",
                "sarathi": "automatic routing",
                "sarathi-explicit": "explicit",
            }[args.condition],
            "isolation": "ephemeral session in an empty temporary directory",
            "tasks": args.tasks,
            "reps": args.n,
            "jobs": args.jobs,
            "command": " ".join(sys.argv),
        },
        "summary": summarize(rows),
        "results": rows,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{stamp}-{args.condition}.json"
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    summary = artifact["summary"]
    rate = summary["pass_rate"]
    print(f"pass rate: {summary['passed']}/{summary['valid']} ({rate:.1%})" if rate is not None else "no valid calls")
    print(f"skill read in {summary['skill_loaded_calls']}/{summary['valid']} calls")
    print(f"raw: {path}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
