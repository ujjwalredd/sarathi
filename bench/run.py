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
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "bench/tasks"
ARMS_DIR = ROOT / "bench/arms"
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
    path = ARMS_DIR / f"{arm}.txt"
    if not path.exists():
        raise FileNotFoundError(f"arm {arm} is missing; run bench/build_arms.py")
    return path.read_text(encoding="utf-8")


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
                r"\bshouldn't\b|\bnever\b|\bavoid\b|\brefuse to\b)"
                r"[^.!?\n;:]{0,60}$",
                prefix,
                re.IGNORECASE,
            )
            negated_after = re.match(
                r"[^.!?\n;:]{0,90}\b(?:I|we)?\s*"
                r"(?:would|will|should|must)\s+not\s+"
                r"(?:do|take|use|choose|ship|apply|recommend)\b",
                suffix,
                re.IGNORECASE,
            )
            if not (negated_before or negated_after):
                violations.append(f"found: /{pattern}/ → {match.group(0)[:50]!r}")
                break
    return (not violations, violations)


def run_one(task: dict, arm_text: str, timeout: int, workspace: Path) -> tuple[str, dict]:
    """Run one task in one arm. Returns (output_text, usage_metadata).

    Uses --output-format json rather than text because the JSON envelope carries
    exact per-call token counts, cost, and model id. The earlier text-based
    version could not attribute tokens to arms at all: every call writes to the
    same session directory, so there was nothing for net.py to separate.
    """
    prompt = f"{arm_text}\n\n{SCENARIO_PREAMBLE}{task['prompt']}"
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode:
            detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no stderr"
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


def report(results: list[Result], arms: Sequence[str]) -> None:
    print("\n  pass rate by arm")
    print("  " + "─" * 64)
    rates = {}
    for arm in arms:
        subset = [r for r in results if r.arm == arm]
        if not subset:
            continue
        rate = sum(r.passed for r in subset) / len(subset)
        rates[arm] = rate
        label = {"A": "control", "B": "spelled out", "C": "anchored"}.get(arm, "")
        print(f"  {arm}  {rate:6.1%}   n={len(subset):<4} {label}")

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
        print(f"  {'arm':<5}{'out tok':>10}{'fresh in':>10}{'cache rd':>11}{'$/call':>10}")
        for arm in arms:
            subset = [r for r in usable if r.arm == arm]
            if not subset:
                continue
            out = statistics.fmean(r.usage["output_tokens"] for r in subset)
            fresh = statistics.fmean(r.usage["input_tokens"] for r in subset)
            cread = statistics.fmean(r.usage["cache_read_input_tokens"] for r in subset)
            cost = statistics.fmean(r.usage["cost_usd"] for r in subset)
            print(f"  {arm:<5}{out:>10.0f}{fresh:>10.0f}{cread:>11.0f}{cost:>10.4f}")
        print("  " + "─" * 64)
        print("  note: inside Claude Code every call carries a ~11k-token system")
        print("  prompt, so the arm difference (B−C ≈ 434 tok) is a small share of")
        print("  total spend here. The compression matters far more in a lean API")
        print("  context than inside a heavyweight agent harness. Report both.")

    def delta(x: str, y: str) -> str:
        if x not in rates or y not in rates:
            return "n/a"
        return f"{rates[x] - rates[y]:+.1%}"

    print("\n  comparisons")
    print("  " + "─" * 64)
    if "A" in rates and "B" in rates:
        print(f"  B − A  {delta('B','A'):>8}   do the principles help at all?")
    if "B" in rates and "C" in rates:
        print(f"  C − B  {delta('C','B'):>8}   does the pointer carry the spelled-out principle?")
    if "C" in rates and "E" in rates:
        print(f"  C − E  {delta('C','E'):>8}   does the reference beat the label alone?")
    if "C" in rates and "D" in rates:
        print(f"  C − D  {delta('C','D'):>8}   does a correct reference beat an incorrect one?")

    print("\n  reading")
    print("  " + "─" * 64)
    if "A" in rates and "B" in rates and rates["B"] - rates["A"] < 0.05:
        print("  ⚠  B ≈ A. The principles show no effect on this suite, so every")
        print("     later comparisons cannot show much. Improve the tasks first.")
    if "C" in rates and "E" in rates:
        if abs(rates["C"] - rates["E"]) < 0.05:
            print("  C ≈ E. The English label carries the meaning; the verse reference")
            print("  adds nothing measurable. The labels work, but the references")
            print("  add no demonstrated value.")
        elif rates["C"] > rates["E"]:
            print("  C > E. The reference contributes beyond the label. This is the")
            print("  result the project was built to find.")
        else:
            print("  C < E. The reference performs worse than a bare label, probably")
            print("  register contamination. Check output length and tone in arm C.")
    if "C" in rates and "D" in rates and abs(rates["C"] - rates["D"]) < 0.05:
        print("  C ≈ D. A wrong reference performs like a correct one, so the model")
        print("  is responding to reference SHAPE, not to the verse. Fatal for the")
        print("  compression claim even if C beats E.")
    print()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Five-arm experiment driver. Makes real API calls.")
    parser.add_argument("--arms", nargs="+", default=["A", "B", "C", "D", "E"])
    parser.add_argument("--tasks", nargs="+", default=["reasoning"])
    parser.add_argument("--n", type=int, default=1, help="repetitions per task per arm")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--jobs", type=int, default=3, help="concurrent calls (default 3)")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    if not shutil.which("claude"):
        print("error: `claude` CLI not found on PATH", file=sys.stderr)
        return 1

    tasks = load_tasks(args.tasks)
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

    def execute(job, workspace: Path):
        arm, rep, task = job
        output, usage = run_one(task, arm_texts[arm], args.timeout, workspace)
        passed, violations = score(task, output)
        if not usage:
            passed = False
            violations.append("API call returned no usage metadata")
        return Result(task["id"], task["anchor"], arm, rep, passed, violations, output, usage)

    print()
    results: list[Result] = []
    done = 0
    with tempfile.TemporaryDirectory(prefix="sarathi-claude-bench-") as tmp:
        workspace = Path(tmp)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(execute, job, workspace): job for job in jobs}
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
    meta = {
        "timestamp": stamp,
        "claude_code_version": probe(["claude", "--version"]),
        "model": ",".join(models) if models else "unknown",
        "arms": list(args.arms),
        "tasks": list(args.tasks),
        "isolation": "hypothetical scenario in an empty temporary directory",
        "reps": args.n,
        "n_per_arm": len(tasks) * args.n,
        "command": " ".join(sys.argv),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps([r.__dict__ for r in results], indent=2), encoding="utf-8"
    )
    print(f"\n  model: {meta['model']}   claude code: {meta['claude_code_version']}")

    report(results, args.arms)
    print(f"  raw: {run_dir / 'results.json'}")
    print("  exact per-call token and cost metadata is included in the raw artifact\n")
    failed_calls = sum(not result.usage for result in results)
    if failed_calls:
        print(f"  error: {failed_calls} call(s) returned no usage metadata; run is invalid\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
