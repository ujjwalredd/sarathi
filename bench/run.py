#!/usr/bin/env python3
"""Five-arm driver for the sarathi experiment.

    arm A   no guidance                  control
    arm B   principles spelled out       does the guidance help at all?
    arm C   label + verse reference      does the pointer carry the same weight?
    arm D   label + wrong reference      does reference correctness matter?
    arm E   label only                   does the reference add beyond the label?

A vs B answers whether the principles are worth anything. B vs C is the thesis:
same content, different encoding, ~4x fewer tokens. If C matches B, references
work as compression. If C trails B, the short references lost useful guidance.

Results break down per anchor rather than only in aggregate, because a mean
would hide the interesting case - some pointers resolving and others not.

Cost warning: real API calls. Start with --n 1 to shake out the harness.

Usage:
    python bench/run.py --n 3
    python bench/run.py --arms B C --n 5
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

import analyze
import build_arms
import stats
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "bench/tasks"
SCENARIO_PREAMBLE = (
    "Treat the following as a hypothetical engineering decision scenario. "
    "No project files are available. Do not inspect a workspace or run tools; "
    "state the response and actions you would take.\n\n"
)


@dataclass
class Result:
    task_id: str
    anchor: str
    arm: str
    rep: int
    passed: bool
    violations: list[str]
    output: str
    usage: dict


def load_tasks(names: Sequence[str]) -> list[dict]:
    tasks = []
    for name in names:
        path = TASKS_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"no task file: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        for task in data.get("tasks", []):
            task.setdefault("required", [])
            task.setdefault("forbidden", [])
            task.setdefault("anchor", "unmapped")
            tasks.append(task)
    return tasks


def load_arm(arm: str) -> str:
    arms = build_arms.build_all()
    try:
        return arms[arm]
    except KeyError as exc:
        raise ValueError(f"unknown arm: {arm}") from exc


def score(task: dict, output: str) -> tuple[bool, list[str]]:
    violations = []
    for pattern in task["required"]:
        if not re.search(pattern, output, re.IGNORECASE | re.MULTILINE | re.DOTALL):
            violations.append(f"missing: /{pattern}/")
    for pattern in task["forbidden"]:
        matches = re.finditer(pattern, output, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in matches:
            # A correct answer often names the tempting shortcut while rejecting
            # it ("do not skip the test"). Counting that as a violation reverses
            # the task's meaning. Treat a match as negated only when a clear
            # negator occurs in the same clause immediately before it.
            prefix = output[max(0, match.start() - 80):match.start()]
            suffix = output[match.end():match.end() + 120]
            negated_before = re.search(
                r"(?:\bdo not\b|\bdon't\b|\bwould not\b|\bwouldn't\b|"
                r"\bwill not\b|\bwon't\b|\bmust not\b|\bshould not\b|"
                r"\bshouldn't\b|\bnever\b|\bavoid\b|\brefuse to\b|"
                r"\bno need (?:to|for)\b|\bwithout\b|\brather than\b|"
                r"\binstead of\b)"
                r"[^.!?\n;:]{0,60}$",
                prefix,
                re.IGNORECASE,
            )
            negated_inside = re.search(
                r"\b(?:not|never|avoid|without|rather than|instead of|unnecessary|overkill)\b",
                match.group(0),
                re.IGNORECASE,
            )
            negated_after = re.match(
                r"[^.!?\n;:]{0,90}\b(?:I|we)?\s*"
                r"(?:would|will|should|must)\s+not\s+"
                r"(?:do|take|use|choose|ship|apply|recommend)\b",
                suffix,
                re.IGNORECASE,
            )
            if not (negated_before or negated_inside or negated_after):
                violations.append(f"found: /{pattern}/ → {match.group(0)[:50]!r}")
                break
    return (not violations, violations)


def run_one_claude(
    task: dict,
    arm_text: str,
    model: str,
    max_budget_usd: float,
    timeout: int,
    workspace: Path,
) -> tuple[str, dict]:
    """Run one task in one arm. Returns (output_text, usage_metadata).

    Uses --output-format json rather than text because the JSON envelope carries
    exact per-call token counts, cost, and model id. The earlier text-based
    version could not attribute tokens to arms at all: every call writes to the
    same session directory, so there was nothing for net.py to separate.
    """
    prompt = f"{arm_text}\n\n{SCENARIO_PREAMBLE}{task['prompt']}"
    try:
        proc = subprocess.run(
            [
                "claude", "-p", prompt,
                "--output-format", "json",
                "--model", model,
                "--max-budget-usd", str(max_budget_usd),
                "--safe-mode",
                "--tools", "",
                "--no-session-persistence",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode:
            detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
            if proc.stdout.strip():
                try:
                    failure = json.loads(proc.stdout)
                    detail = failure.get("result") or failure.get("terminal_reason") or detail
                except json.JSONDecodeError:
                    detail = proc.stdout.strip().splitlines()[-1][-500:]
            detail = detail or "no diagnostic output"
            print(f"\n  warning: claude exited {proc.returncode} for {task['id']}: {detail}", file=sys.stderr)
            return "", {}
        payload = json.loads(proc.stdout)
        usage = payload.get("usage", {})
        if payload.get("is_error") or not isinstance(usage, dict) or not usage:
            print(f"\n  warning: API error or missing usage for {task['id']}", file=sys.stderr)
            return "", {}
        model = next(iter(payload.get("modelUsage", {})), "unknown")
        if model == "unknown":
            print(f"\n  warning: missing model id for {task['id']}", file=sys.stderr)
            return "", {}
        meta = {
            "input_tokens": usage.get("input_tokens", 0),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cost_usd": payload.get("total_cost_usd", 0.0),
            "model": model,
            "duration_ms": payload.get("duration_ms", 0),
        }
        return payload.get("result", ""), meta
    except subprocess.TimeoutExpired:
        return "", {}
    except json.JSONDecodeError:
        # A non-JSON payload means the call failed in a way worth seeing rather
        # than silently scoring as an empty (and therefore failing) answer.
        print(f"\n  warning: unparseable response for {task['id']}", file=sys.stderr)
        return "", {}
    except FileNotFoundError:
        print("error: `claude` CLI not found on PATH", file=sys.stderr)
        raise SystemExit(1)


def run_one_codex(
    task: dict,
    arm_text: str,
    model: str,
    effort: str,
    timeout: int,
    workspace: Path,
) -> tuple[str, dict]:
    """Run one isolated Codex call. Codex reports tokens but not dollar cost."""
    prompt = f"{arm_text}\n\n{SCENARIO_PREAMBLE}{task['prompt']}"
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
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return "", {}
    except FileNotFoundError:
        print("error: `codex` CLI not found on PATH", file=sys.stderr)
        raise SystemExit(1)

    messages = []
    usage = {}
    parse_errors = []
    for lineno, line in enumerate(proc.stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parse_errors.append(f"line {lineno} is not JSON")
            continue
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                messages.append(item.get("text", ""))
        elif event.get("type") == "turn.completed":
            usage = event.get("usage", {})

    if proc.returncode or parse_errors or not messages or not usage:
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
        if parse_errors:
            detail = ", ".join(parse_errors[:3])
        detail = detail or "missing final message or usage"
        print(f"\n  warning: codex failed for {task['id']}: {detail}", file=sys.stderr)
        return "", {}

    cached = int(usage.get("cached_input_tokens", 0) or 0)
    total_input = int(usage.get("input_tokens", 0) or 0)
    meta = {
        "input_tokens": max(total_input - cached, 0),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cached,
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "reasoning_output_tokens": int(usage.get("reasoning_output_tokens", 0) or 0),
        "model": model,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    return messages[-1], meta


ARM_LABELS = {
    "A": "control, no guidance",
    "B": "sarathi, spelled out",
    "C": "sarathi, anchored",
    "D": "sarathi, wrong refs",
    "E": "sarathi, labels only",
    "F": "caveman",
    "G": "ponytail",
    "H": "sarathi, deployed skill",
}


def report(results: list[Result], arms: Sequence[str], backend: str) -> None:
    print("\n  pass rate by arm, with 95% Wilson intervals")
    print("  " + "─" * 70)
    rates = {}
    counts = {}
    for arm in arms:
        subset = [r for r in results if r.arm == arm]
        if not subset:
            continue
        passed = sum(r.passed for r in subset)
        rates[arm] = passed / len(subset)
        counts[arm] = (passed, len(subset))
        ci = stats.wilson(passed, len(subset))
        print(
            f"  {arm}  {rates[arm]:6.1%}  {stats.fmt_ci(ci)}  n={len(subset):<4}"
            f" {ARM_LABELS.get(arm, '')}"
        )

    print("\n  by anchor")
    print("  " + "─" * 64)
    by_anchor: dict[str, dict[str, list[Result]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in results:
        by_anchor[r.anchor][r.arm].append(r)

    header = "  " + "anchor".ljust(24) + "".join(a.center(10) for a in arms)
    print(header)
    for anchor in sorted(by_anchor):
        cells = []
        for arm in arms:
            subset = by_anchor[anchor][arm]
            cells.append(f"{sum(r.passed for r in subset) / len(subset):.0%}".center(10) if subset else "-".center(10))
        print(f"  {anchor:<24}{''.join(cells)}")

    print("  " + "─" * 64)

    # Token and cost accounting, straight from the JSON envelope of each call.
    usable = [r for r in results if r.usage]
    if usable:
        print("\n  tokens and cost per arm")
        print("  " + "─" * 64)
        print(
            f"  {'arm':<5}{'out tok':>10}{'fresh in':>10}{'cache rd':>11}"
            f"{'tok/pass':>11}{'$/call':>10}{'$/pass':>10}"
        )
        for arm in arms:
            subset = [r for r in usable if r.arm == arm]
            if not subset:
                continue
            out = statistics.fmean(r.usage["output_tokens"] for r in subset)
            fresh = statistics.fmean(r.usage["input_tokens"] for r in subset)
            cread = statistics.fmean(r.usage["cache_read_input_tokens"] for r in subset)
            passed = sum(r.passed for r in subset)
            total_tokens = sum(
                r.usage.get("input_tokens", 0)
                + r.usage.get("cache_creation_input_tokens", 0)
                + r.usage.get("cache_read_input_tokens", 0)
                + r.usage.get("output_tokens", 0)
                for r in subset
            )
            tokens_per_pass = total_tokens / passed if passed else float("nan")
            costs = [r.usage["cost_usd"] for r in subset if "cost_usd" in r.usage]
            cost = statistics.fmean(costs) if len(costs) == len(subset) else float("nan")
            cost_per_pass = sum(costs) / passed if passed and len(costs) == len(subset) else float("nan")
            cost_text = f"{cost:.4f}" if cost == cost else "n/a"
            cpp = f"{cost_per_pass:.4f}" if cost_per_pass == cost_per_pass else "n/a"
            tpp = f"{tokens_per_pass:.0f}" if tokens_per_pass == tokens_per_pass else "n/a"
            print(
                f"  {arm:<5}{out:>10.0f}{fresh:>10.0f}{cread:>11.0f}"
                f"{tpp:>11}{cost_text:>10}{cpp:>10}"
            )
        print("  " + "─" * 64)
        print(f"  note: {backend} system context can dominate token usage, so an")
        print("  arm's prompt and visible output are only part of total spend.")
        print("  $/pass is a point estimate, not proof when pass intervals are wide.")

    def compare(x: str, y: str, question: str) -> None:
        if x not in counts or y not in counts:
            return
        px, nx = counts[x]
        py, ny = counts[y]
        ci = stats.newcombe(px, nx, py, ny)
        diff = rates[x] - rates[y]
        mark = "*" if stats.significant(ci) else " "
        print(f"  {x} - {y}  {diff:+6.1%}  {stats.fmt_ci(ci)} {mark}  {question}")

    print("\n  comparisons  (* = interval excludes zero)")
    print("  " + "\u2500" * 70)
    compare("B", "A", "do the principles help at all?")
    compare("C", "B", "does the pointer carry the spelled-out principle?")
    compare("C", "E", "does the reference beat the label alone?")
    compare("C", "D", "does a CORRECT reference beat a wrong one?")
    compare("C", "A", "sarathi vs no guidance")
    compare("C", "F", "sarathi vs caveman")
    compare("C", "G", "sarathi vs ponytail")
    compare("H", "A", "deployed sarathi vs no guidance")
    compare("H", "F", "deployed sarathi vs caveman")
    compare("H", "G", "deployed sarathi vs ponytail")

    # Power. Without this the reader cannot tell "no effect" from "no resolution".
    if "A" in rates and rates["A"] not in (0.0, 1.0):
        n_here = counts["A"][1]
        for effect in (0.15, 0.25, 0.35):
            need = stats.required_n(rates["A"], effect)
            if need <= n_here:
                detectable = effect
                break
        else:
            detectable = None
        print("\n  power")
        print("  " + "\u2500" * 70)
        print(f"  n={n_here} per arm detects roughly "
              + (f"{detectable:.0%}+ effects." if detectable else "only very large effects."))
        print(f"  to detect +15pp at 80% power you would need n="
              f"{stats.required_n(rates['A'], 0.15)} per arm.")
        print("  intervals that span zero mean NO EVIDENCE of a difference,")
        print("  which is not the same as evidence of no difference.")
    print()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated multi-arm experiment driver. Makes real model calls.")
    parser.add_argument("--backend", choices=["claude", "codex"], default="claude")
    parser.add_argument("--arms", nargs="+", default=["A", "B", "C", "D", "E"])
    parser.add_argument("--tasks", nargs="+", default=["reasoning"])
    parser.add_argument("--task-ids", nargs="+", help="optional exact task ids for a smoke run")
    parser.add_argument("--n", type=int, default=1, help="repetitions per task per arm")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--jobs", type=int, default=3, help="concurrent calls (default 3)")
    parser.add_argument("--model", default="opus", help="exact model id or Claude alias")
    parser.add_argument("--effort", default="medium", help="Codex reasoning effort")
    parser.add_argument("--max-budget-per-call", type=float, default=0.50)
    parser.add_argument("--seed", type=int, default=1729, help="deterministic job-order seed")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    if not shutil.which(args.backend):
        print(f"error: `{args.backend}` CLI not found on PATH", file=sys.stderr)
        return 1
    if args.n < 1 or args.jobs < 1 or args.max_budget_per_call <= 0:
        parser.error("--n, --jobs, and --max-budget-per-call must be positive")

    tasks = load_tasks(args.tasks)
    if args.task_ids:
        requested = set(args.task_ids)
        available = {task["id"] for task in tasks}
        missing = sorted(requested - available)
        if missing:
            parser.error(f"unknown --task-ids: {', '.join(missing)}")
        tasks = [task for task in tasks if task["id"] in requested]
    arm_texts = {arm: load_arm(arm) for arm in args.arms}
    total = len(tasks) * args.n * len(args.arms)

    print(f"\n  {len(tasks)} tasks × {args.n} reps × {len(args.arms)} arms = {total} API calls")
    if not args.yes:
        if input("  this costs real money. proceed? [y/N] ").strip().lower() != "y":
            print("  aborted")
            return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = args.out / stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build the full job list first so results can be reassembled in a
    # deterministic order regardless of completion order - a run must be
    # reproducible, and thread scheduling is not.
    jobs = [
        (arm, rep, task)
        for arm in args.arms
        for rep in range(args.n)
        for task in tasks
    ]
    random.Random(args.seed).shuffle(jobs)

    def execute(job, workspace: Path):
        arm, rep, task = job
        if args.backend == "claude":
            output, usage = run_one_claude(
                task,
                arm_texts[arm],
                args.model,
                args.max_budget_per_call,
                args.timeout,
                workspace,
            )
        else:
            output, usage = run_one_codex(
                task,
                arm_texts[arm],
                args.model,
                args.effort,
                args.timeout,
                workspace,
            )
        passed, violations = score(task, output)
        if not usage:
            passed = False
            violations.append("API call returned no usage metadata")
        return Result(task["id"], task["anchor"], arm, rep, passed, violations, output, usage)

    print()
    results: list[Result] = []
    done = 0
    with tempfile.TemporaryDirectory(prefix=f"sarathi-{args.backend}-bench-") as tmp:
        workspace_root = Path(tmp)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {}
            for index, job in enumerate(jobs):
                arm, rep, task = job
                workspace = workspace_root / f"{index:04d}-{arm}-{rep}-{task['id']}"
                workspace.mkdir()
                futures[pool.submit(execute, job, workspace)] = job
            for future in concurrent.futures.as_completed(futures):
                arm, rep, task = futures[future]
                result = future.result()
                results.append(result)
                done += 1
                status = "pass" if result.passed else "FAIL"
                print(f"  [{done:>3}/{len(jobs)}] {arm} rep{rep + 1} {task['id']:<22} {status}")

    # Deterministic ordering for the artifact.
    order = {arm: i for i, arm in enumerate(args.arms)}
    results.sort(key=lambda r: (order[r.arm], r.rep, r.task_id))

    # Metadata is not optional. Anchoring depends on training-data
    # representation, so a result without a model id is not a result.
    def probe(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return "unknown"

    models = sorted({
        r.usage.get("model")
        for r in results
        if r.usage.get("model") and r.usage.get("model") != "unknown"
    })

    def file_record(path: Path) -> dict:
        data = path.read_bytes()
        return {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

    def generated_arm_record(arm: str, content: str) -> dict:
        data = content.encode("utf-8")
        return {
            "arm": arm,
            "generated_by": "bench/build_arms.py",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }

    manifest = {
        "arms": {arm: generated_arm_record(arm, arm_texts[arm]) for arm in args.arms},
        "tasks": {name: file_record(TASKS_DIR / f"{name}.json") for name in args.tasks},
        "scorer": file_record(ROOT / "bench/run.py"),
        "sarathi_skill": file_record(ROOT / "skills/sarathi/SKILL.md"),
    }
    provenance = ROOT / "bench/vendor/provenance.json"
    if provenance.exists():
        manifest["competitor_provenance"] = file_record(provenance)

    failed_calls = sum(not result.usage for result in results)
    meta = {
        "timestamp": stamp,
        "backend": args.backend,
        "backend_version": probe([args.backend, "--version"]),
        "model": ",".join(models) if models else "unknown",
        "requested_model": args.model,
        "reasoning_effort": args.effort if args.backend == "codex" else None,
        "arms": list(args.arms),
        "tasks": list(args.tasks),
        "task_ids": [task["id"] for task in tasks],
        "isolation": "hypothetical scenario in a fresh empty temporary directory per call",
        "reps": args.n,
        "n_per_arm": len(tasks) * args.n,
        "seed": args.seed,
        "max_budget_per_call_usd": args.max_budget_per_call,
        "isolation_flags": (
            ["--safe-mode", "--tools", "", "--no-session-persistence"]
            if args.backend == "claude"
            else ["--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only"]
        ),
        "manifest": manifest,
        "valid": failed_calls == 0,
        "failed_calls": failed_calls,
        "command": " ".join(sys.argv),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps([r.__dict__ for r in results], indent=2), encoding="utf-8"
    )
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(analyze.analyze(run_dir), indent=2) + "\n", encoding="utf-8")
    print(f"\n  model: {meta['model']}   {meta['backend']}: {meta['backend_version']}")

    report(results, args.arms, args.backend)
    print(f"  raw: {run_dir / 'results.json'}")
    print(f"  summary: {summary_path}")
    print("  exact per-call token and cost metadata is included in the raw artifact\n")
    if failed_calls:
        print(f"  error: {failed_calls} call(s) returned no usage metadata; run is invalid\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
