#!/usr/bin/env python3
"""Executable, isolated repository-task benchmark for agent skills.

Each arm receives the same starter repository and natural-language request.
Hidden tests are kept outside the agent workspace and run only after Codex exits.
Raw run artifacts are local-only under results/.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import json
import os
import random
import re
import resource
import signal
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

import build_arms
import stats


ROOT = Path(__file__).resolve().parent.parent
TASKS_ROOT = ROOT / "bench/repo_tasks"
RESULTS_ROOT = ROOT / "results/repo"
TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_FILES = 32
MAX_FILE_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 2_000_000
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".agent-tmp"}
IGNORED_FILES = {".coverage", ".DS_Store"}
SOURCE_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).resolve()
SAFE_PATH = f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin"

ARM_LABELS = {
    "A": "control",
    "F": "Caveman",
    "G": "Ponytail",
    "H": "Sarathi",
}


@dataclasses.dataclass(frozen=True)
class Task:
    task_id: str
    prompt: str
    directory: Path
    starter: Path
    hidden_test: Path


@dataclasses.dataclass
class Result:
    task_id: str
    arm: str
    rep: int
    status: str
    passed: bool
    usage: dict
    duration_ms: int
    changed_files: list[str]
    final_message: str
    agent_stderr: str
    grader_stdout: str
    grader_stderr: str
    grader_returncode: int | None
    candidate_manifest: dict[str, str] = dataclasses.field(default_factory=dict)
    candidate_snapshot: str | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
    }


def regular_files(root: Path) -> list[Path]:
    """Return a bounded, symlink-free tree of regular files."""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"special file is not allowed: {path}")
        if path.stat().st_nlink != 1:
            raise ValueError(f"hard-linked file is not allowed: {path}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes: {path}")
        files.append(path)
        if len(files) > MAX_FILES:
            raise ValueError(f"tree exceeds {MAX_FILES} files: {root}")
    return files


def tree_manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in regular_files(root)
    }


def remove_generated_artifacts(root: Path) -> None:
    """Remove only known interpreter and test-runner cache artifacts."""
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {path}")
        if path.is_dir() and path.name in IGNORED_DIRS:
            shutil.rmtree(path)
        elif path.is_file() and (path.name in IGNORED_FILES or path.suffix in {".pyc", ".pyo"}):
            path.unlink()


def load_tasks(suite: str, task_ids: Sequence[str] | None = None) -> list[Task]:
    if not TASK_ID_RE.fullmatch(suite):
        raise ValueError(f"invalid suite name: {suite!r}")
    suite_dir = TASKS_ROOT / suite
    if not suite_dir.is_dir():
        raise FileNotFoundError(f"no task suite: {suite_dir}")

    selected = set(task_ids or ())
    tasks: list[Task] = []
    for directory in sorted(suite_dir.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"suite contains an invalid entry: {directory}")
        task_id = directory.name
        if not TASK_ID_RE.fullmatch(task_id):
            raise ValueError(f"invalid task id: {task_id!r}")
        if selected and task_id not in selected:
            continue
        prompt_path = directory / "prompt.txt"
        starter = directory / "starter"
        hidden_test = directory / "hidden_test.py"
        if not prompt_path.is_file() or not starter.is_dir() or not hidden_test.is_file():
            raise ValueError(f"task is incomplete: {directory}")
        regular_files(starter)
        if not tree_manifest(starter):
            raise ValueError(f"task has no starter files: {directory}")
        prompt = prompt_path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise ValueError(f"task has an empty prompt: {directory}")
        tasks.append(Task(task_id, prompt, directory, starter, hidden_test))

    available = {path.name for path in suite_dir.iterdir() if path.is_dir()}
    missing = selected - available
    if missing:
        raise ValueError(f"unknown task ids: {', '.join(sorted(missing))}")
    if not tasks:
        raise ValueError("no tasks selected")
    return tasks


def build_prompt(task: Task, arm_text: str) -> str:
    guidance = arm_text.rstrip()
    prefix = f"{guidance}\n\n" if guidance else ""
    return (
        prefix
        + "Work on the isolated repository in your current directory. "
        + "Implement the request in the files, not just in your final response. "
        + "Inspect the starter code, make the smallest correct change, and run useful local checks. "
        + "Do not install dependencies or access the network. Keep the final response concise.\n\n"
        + task.prompt
        + "\n"
    )


def parse_codex_jsonl(stdout: str) -> tuple[str, dict, list[str]]:
    messages: list[str] = []
    usage: dict = {}
    errors: list[str] = []
    for line_number, line in enumerate(stdout.splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {line_number} is not JSON")
            continue
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                messages.append(str(item.get("text", "")))
        elif event.get("type") == "turn.completed":
            raw = event.get("usage")
            if isinstance(raw, dict):
                usage = raw
    if not messages:
        errors.append("missing final agent message")
    if not usage:
        errors.append("missing token usage")
    return (messages[-1] if messages else "", usage, errors)


def shell_environment_config(workspace: Path) -> str:
    scratch = workspace / ".agent-tmp"
    values = {
        "PATH": SAFE_PATH,
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    assignments = ", ".join(f"{key} = {json.dumps(value)}" for key, value in values.items())
    return "{" + assignments + "}"


def codex_command(workspace: Path, model: str, effort: str) -> list[str]:
    return [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--disable",
        "plugins",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{effort}"',
        "--config",
        'shell_environment_policy.inherit="none"',
        "--config",
        f"shell_environment_policy.set={shell_environment_config(workspace)}",
        "--cd",
        str(workspace),
        "-",
    ]


def grader_command(workspace: Path) -> list[str]:
    scratch = workspace / ".grader-tmp"
    scratch.mkdir(mode=0o700, exist_ok=False)
    return [
        "codex",
        "sandbox",
        "-P",
        ":workspace",
        "-C",
        str(workspace),
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        f"HOME={scratch}",
        f"TMPDIR={scratch}",
        "PYTHONDONTWRITEBYTECODE=1",
        sys.executable,
        "-I",
        "-B",
        "-",
    ]


def remove_grader_scratch(workspace: Path) -> None:
    scratch = workspace / ".grader-tmp"
    if scratch.is_symlink():
        scratch.unlink()
    elif scratch.is_dir():
        shutil.rmtree(scratch)
    elif scratch.exists():
        scratch.unlink()


def resource_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (5_000_000, 5_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def terminate_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def skipped_test_count(output: str) -> int:
    matches = re.findall(r"\bskipped=(\d+)\b", output)
    return max((int(value) for value in matches), default=0)


def token_counts(usage: dict) -> tuple[int, int, int]:
    """Return fresh input, cached input, and output counts from Codex usage."""
    cached = int(usage.get("cached_input_tokens", 0))
    fresh = max(int(usage.get("input_tokens", 0)) - cached, 0)
    output = int(usage.get("output_tokens", 0))
    return fresh, cached, output


def estimated_api_cost(usage: dict, pricing: dict | None) -> float | None:
    """Estimate API-equivalent cost from explicit per-million-token rates."""
    if pricing is None:
        return None
    fresh, cached, output = token_counts(usage)
    threshold = pricing.get("long_context_threshold_tokens")
    long_context = threshold is not None and fresh + cached > threshold
    input_multiplier = pricing.get("long_context_input_multiplier", 1.0) if long_context else 1.0
    output_multiplier = pricing.get("long_context_output_multiplier", 1.0) if long_context else 1.0
    return (
        fresh * pricing["fresh_input_usd_per_million"] * input_multiplier
        + cached * pricing["cached_input_usd_per_million"] * input_multiplier
        + output * pricing["output_usd_per_million"] * output_multiplier
    ) / 1_000_000


def summarize_results(
    results: Sequence[Result], arms: Sequence[str], pricing: dict | None
) -> dict:
    """Build the machine-readable result table used by reports and charts."""
    summary = {"pricing": pricing, "arms": {}, "comparisons": {}}
    for arm in arms:
        valid = [item for item in results if item.arm == arm and item.status != "infrastructure-invalid"]
        measured = [item for item in results if item.arm == arm and item.usage]
        passed = sum(item.passed for item in valid)
        fresh, cached, output = zip(*(token_counts(item.usage) for item in measured)) if measured else ((), (), ())
        raw_total = sum(fresh) + sum(cached) + sum(output)
        costs = [estimated_api_cost(item.usage, pricing) for item in measured]
        cost_total = sum(value for value in costs if value is not None) if pricing else None
        interval = stats.wilson(passed, len(valid)) if valid else (None, None)
        summary["arms"][arm] = {
            "label": ARM_LABELS.get(arm, arm),
            "passed": passed,
            "valid": len(valid),
            "infrastructure_invalid": sum(
                item.arm == arm and item.status == "infrastructure-invalid" for item in results
            ),
            "pass_rate": passed / len(valid) if valid else None,
            "pass_rate_wilson_95": list(interval),
            "mean_fresh_input_tokens": statistics.fmean(fresh) if fresh else None,
            "mean_cached_input_tokens": statistics.fmean(cached) if cached else None,
            "mean_output_tokens": statistics.fmean(output) if output else None,
            "raw_tokens_per_verified_pass": raw_total / passed if passed else None,
            "mean_duration_ms": statistics.fmean(item.duration_ms for item in measured) if measured else None,
            "estimated_api_cost_total_usd": cost_total,
            "estimated_api_cost_per_verified_pass_usd": cost_total / passed
            if cost_total is not None and passed
            else None,
        }

    sarathi = summary["arms"].get("H")
    if sarathi and sarathi["valid"]:
        for rival in ("A", "F", "G"):
            other = summary["arms"].get(rival)
            if not other or not other["valid"]:
                continue
            interval = stats.newcombe(
                sarathi["passed"], sarathi["valid"], other["passed"], other["valid"]
            )
            comparison = {
                "pass_rate_delta": sarathi["pass_rate"] - other["pass_rate"],
                "pass_rate_newcombe_95": list(interval),
                "pass_rate_significant": stats.significant(interval),
            }
            for field in (
                "raw_tokens_per_verified_pass",
                "estimated_api_cost_per_verified_pass_usd",
                "mean_duration_ms",
            ):
                baseline = other[field]
                value = sarathi[field]
                comparison[f"{field}_delta_fraction"] = (
                    value / baseline - 1 if value is not None and baseline else None
                )
            summary["comparisons"][f"H_vs_{rival}"] = comparison
    return summary


def grade(
    task: Task,
    workspace: Path,
    timeout: int,
    codex_env: dict[str, str],
) -> tuple[bool, int | None, str, str, str]:
    hidden = task.hidden_test.read_text(encoding="utf-8")
    program = "import os, sys\nsys.path.insert(0, os.getcwd())\n" + hidden
    proc = subprocess.Popen(
        grader_command(workspace),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        preexec_fn=resource_limits,
        env=codex_env,
    )
    try:
        stdout, stderr = proc.communicate(program, timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        remove_grader_scratch(workspace)
        stdout = stdout[-MAX_OUTPUT_BYTES:]
        stderr = stderr[-MAX_OUTPUT_BYTES:]
        return False, None, str(stdout), str(stderr), "candidate-timeout"
    stdout = stdout[-MAX_OUTPUT_BYTES:]
    stderr = stderr[-MAX_OUTPUT_BYTES:]
    remove_grader_scratch(workspace)
    if proc.returncode == 0 and skipped_test_count(stdout + "\n" + stderr):
        return False, proc.returncode, stdout, stderr, "infrastructure-invalid"
    return proc.returncode == 0, proc.returncode, stdout, stderr, "pass" if proc.returncode == 0 else "candidate-fail"


def sandbox_preflight(root: Path, timeout: int, codex_env: dict[str, str]) -> dict:
    workspace = root / "sandbox-preflight"
    workspace.mkdir()
    script = f"""
import pathlib
import socket

pathlib.Path('inside.txt').write_text('ok', encoding='utf-8')
blocked = []
for target in ({str(ROOT / '.repo-bench-write-probe')!r}, {str(Path.home() / '.repo-bench-write-probe')!r}):
    try:
        pathlib.Path(target).write_text('unsafe', encoding='utf-8')
    except OSError:
        blocked.append(target)
try:
    socket.create_connection(('example.com', 80), timeout=1)
except OSError:
    blocked.append('network')
if len(blocked) != 3:
    raise SystemExit('sandbox negative control failed: ' + repr(blocked))
print('sandbox preflight passed')
"""
    proc = subprocess.run(
        grader_command(workspace),
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=codex_env,
    )
    record = {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "passed": proc.returncode == 0,
    }
    if proc.returncode:
        raise RuntimeError(f"sandbox preflight failed: {record}")
    return record


def run_one(
    task: Task,
    arm: str,
    arm_text: str,
    rep: int,
    model: str,
    effort: str,
    agent_timeout: int,
    grader_timeout: int,
    workspace: Path,
    codex_env: dict[str, str],
) -> Result:
    shutil.copytree(task.starter, workspace)
    before = tree_manifest(workspace)
    (workspace / ".agent-tmp").mkdir(mode=0o700)
    prompt = build_prompt(task, arm_text)
    started = time.monotonic()
    proc = subprocess.Popen(
        codex_command(workspace, model, effort),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=codex_env,
    )
    try:
        stdout, stderr = proc.communicate(prompt, timeout=agent_timeout)
    except subprocess.TimeoutExpired:
        terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        return Result(
            task.task_id, arm, rep, "infrastructure-invalid", False, {},
            round((time.monotonic() - started) * 1000), [], "",
            stderr[-MAX_OUTPUT_BYTES:], "", "", None,
        )

    duration_ms = round((time.monotonic() - started) * 1000)
    message, usage, parse_errors = parse_codex_jsonl(stdout)
    if proc.returncode or parse_errors:
        detail = "; ".join(parse_errors)
        stderr = (stderr + ("\n" + detail if detail else ""))[-MAX_OUTPUT_BYTES:]
        return Result(
            task.task_id, arm, rep, "infrastructure-invalid", False, usage,
            duration_ms, [], message, stderr, "", "", None,
        )

    try:
        remove_generated_artifacts(workspace)
        after = tree_manifest(workspace)
    except ValueError as exc:
        return Result(
            task.task_id, arm, rep, "candidate-invalid", False, usage,
            duration_ms, [], message, stderr[-MAX_OUTPUT_BYTES:], "", str(exc), None,
        )
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    if removed or not changed:
        reason = f"added={added}, removed={removed}, changed={changed}"
        return Result(
            task.task_id, arm, rep, "candidate-invalid", False, usage,
            duration_ms, changed + added, message, stderr[-MAX_OUTPUT_BYTES:], "", reason, None,
        )

    agent_stderr = stderr
    passed, returncode, grader_stdout, grader_stderr, status = grade(
        task, workspace, grader_timeout, codex_env
    )
    return Result(
        task.task_id, arm, rep, status, passed, usage, duration_ms, changed + added,
        message, agent_stderr[-MAX_OUTPUT_BYTES:], grader_stdout, grader_stderr, returncode,
    )


def prepare_isolated_codex_home(root: Path) -> tuple[Path, dict[str, str]]:
    codex_home = root / "codex-home"
    codex_home.mkdir(mode=0o700)
    source_auth = SOURCE_CODEX_HOME / "auth.json"
    if source_auth.is_file():
        target_auth = codex_home / "auth.json"
        shutil.copyfile(source_auth, target_auth)
        target_auth.chmod(0o600)
    elif not os.environ.get("CODEX_API_KEY") and not os.environ.get("CODEX_ACCESS_TOKEN"):
        raise RuntimeError(
            f"no file authentication at {source_auth} and no one-run Codex credential in the environment"
        )
    codex_env = os.environ.copy()
    codex_env["HOME"] = str(codex_home)
    codex_env["CODEX_HOME"] = str(codex_home)
    return codex_home, codex_env


def visible_prompt_text(payload) -> str:
    texts: list[str] = []

    def collect(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "text" and isinstance(item, str):
                    texts.append(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload)
    return "\n".join(texts)


def skill_isolation_preflight(root: Path, codex_env: dict[str, str]) -> dict:
    proc = subprocess.run(
        ["codex", "debug", "prompt-input", "isolation-probe"],
        cwd=root,
        env=codex_env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"skill-isolation preflight failed: {proc.stderr[-2000:]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"skill-isolation preflight returned invalid JSON: {exc}") from exc
    rendered = visible_prompt_text(payload)
    forbidden = {
        name: bool(re.search(rf"(?m)^- {re.escape(name)}:", rendered))
        for name in ("sarathi", "caveman", "ponytail")
    }
    if any(forbidden.values()):
        raise RuntimeError(f"competitor skill leaked into isolated prompt: {forbidden}")
    return {
        "passed": True,
        "forbidden_skills_visible": forbidden,
        "prompt_sha256": sha256_bytes(proc.stdout.encode("utf-8")),
    }


def report(results: Sequence[Result], arms: Sequence[str], pricing: dict | None) -> None:
    print("\n  executable hidden-test results")
    print("  " + "-" * 76)
    counts: dict[str, tuple[int, int]] = {}
    for arm in arms:
        valid = [result for result in results if result.arm == arm and result.status != "infrastructure-invalid"]
        invalid = sum(result.arm == arm and result.status == "infrastructure-invalid" for result in results)
        passed = sum(result.passed for result in valid)
        counts[arm] = (passed, len(valid))
        rate = passed / len(valid) if valid else float("nan")
        interval = stats.wilson(passed, len(valid)) if valid else (float("nan"), float("nan"))
        label = ARM_LABELS.get(arm, arm)
        print(f"  {arm}  {label:<10} {passed:>2}/{len(valid):<2}  {rate:>6.1%}  {stats.fmt_ci(interval)}  infra-invalid={invalid}")

    print("\n  measured tokens")
    print("  " + "-" * 76)
    print(f"  {'arm':<5}{'fresh in':>12}{'cache in':>12}{'output':>12}{'total/pass':>14}")
    for arm in arms:
        subset = [result for result in results if result.arm == arm and result.usage]
        if not subset:
            continue
        fresh, cached, output = zip(*(token_counts(item.usage) for item in subset))
        passed = sum(item.passed for item in subset)
        total = sum(a + b + c for a, b, c in zip(fresh, cached, output))
        per_pass = f"{total / passed:.0f}" if passed else "n/a"
        print(
            f"  {arm:<5}{statistics.fmean(fresh):>12.0f}{statistics.fmean(cached):>12.0f}"
            f"{statistics.fmean(output):>12.0f}{per_pass:>14}"
        )

    if pricing:
        print("\n  estimated API-equivalent cost")
        print("  " + "-" * 76)
        print(f"  {'arm':<5}{'mean/call':>16}{'total':>16}{'cost/pass':>16}")
        for arm in arms:
            subset = [result for result in results if result.arm == arm and result.usage]
            costs = [estimated_api_cost(item.usage, pricing) for item in subset]
            if not costs:
                continue
            total = sum(value for value in costs if value is not None)
            passed = sum(item.passed for item in subset)
            per_pass = f"${total / passed:.4f}" if passed else "n/a"
            print(
                f"  {arm:<5}${statistics.fmean(costs):>15.4f}${total:>15.4f}{per_pass:>16}"
            )
        print(f"  source: {pricing['source']}")

    print("\n  Sarathi differences")
    print("  " + "-" * 76)
    hp, hn = counts.get("H", (0, 0))
    for rival in ("A", "F", "G"):
        rp, rn = counts.get(rival, (0, 0))
        if not hn or not rn:
            continue
        difference = hp / hn - rp / rn
        interval = stats.newcombe(hp, hn, rp, rn)
        significance = "yes" if stats.significant(interval) else "no"
        print(f"  H - {rival}: {difference:+.1%}  {stats.fmt_ci(interval)}  significant={significance}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run isolated executable repository tasks through Codex.")
    parser.add_argument("--suite", default="heldout-v2")
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--arms", nargs="+", default=["A", "F", "G", "H"])
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--agent-timeout", type=int, default=600)
    parser.add_argument("--grader-timeout", type=int, default=30)
    parser.add_argument("--seed", type=int, default=240517)
    parser.add_argument("--out", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--fresh-input-usd-per-million", type=float)
    parser.add_argument("--cached-input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    parser.add_argument("--pricing-source")
    parser.add_argument("--long-context-threshold-tokens", type=int)
    parser.add_argument("--long-context-input-multiplier", type=float, default=1.0)
    parser.add_argument("--long-context-output-multiplier", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    if min(args.n, args.jobs, args.agent_timeout, args.grader_timeout) < 1:
        parser.error("counts and timeouts must be positive")
    price_values = (
        args.fresh_input_usd_per_million,
        args.cached_input_usd_per_million,
        args.output_usd_per_million,
    )
    if any(value is not None for value in price_values) != all(
        value is not None for value in price_values
    ):
        parser.error("provide all three token prices or none")
    if any(value is not None and value < 0 for value in price_values):
        parser.error("token prices must be nonnegative")
    if all(value is not None for value in price_values) and not args.pricing_source:
        parser.error("--pricing-source is required with token prices")
    if args.pricing_source and not all(value is not None for value in price_values):
        parser.error("--pricing-source requires all three token prices")
    if args.long_context_threshold_tokens is not None and args.long_context_threshold_tokens < 1:
        parser.error("long-context threshold must be positive")
    if min(args.long_context_input_multiplier, args.long_context_output_multiplier) < 1:
        parser.error("long-context multipliers must be at least 1")
    if args.long_context_threshold_tokens is not None and not all(
        value is not None for value in price_values
    ):
        parser.error("long-context pricing requires all three token prices")
    pricing = (
        {
            "fresh_input_usd_per_million": args.fresh_input_usd_per_million,
            "cached_input_usd_per_million": args.cached_input_usd_per_million,
            "output_usd_per_million": args.output_usd_per_million,
            "source": args.pricing_source,
            "long_context_threshold_tokens": args.long_context_threshold_tokens,
            "long_context_input_multiplier": args.long_context_input_multiplier,
            "long_context_output_multiplier": args.long_context_output_multiplier,
        }
        if all(value is not None for value in price_values)
        else None
    )
    if not shutil.which("codex"):
        parser.error("codex CLI is not installed")

    tasks = load_tasks(args.suite, args.task_ids)
    all_arms = build_arms.build_all()
    unknown = sorted(set(args.arms) - set(all_arms))
    if unknown:
        parser.error(f"unknown arms: {', '.join(unknown)}")
    arm_texts = {arm: all_arms[arm] for arm in args.arms}
    total_calls = len(tasks) * len(args.arms) * args.n
    print(f"\n  suite={args.suite}  {len(tasks)} tasks x {len(args.arms)} arms x {args.n} reps = {total_calls} calls")
    if args.dry_run:
        for task in tasks:
            print(f"  {task.task_id}: {', '.join(tree_manifest(task.starter))}")
        return 0
    if args.preflight_only:
        with tempfile.TemporaryDirectory(prefix="sarathi-repo-bench-preflight-") as temporary:
            temp_root = Path(temporary)
            _codex_home, codex_env = prepare_isolated_codex_home(temp_root)
            skill_check = skill_isolation_preflight(temp_root, codex_env)
            sandbox_check = sandbox_preflight(temp_root, args.grader_timeout, codex_env)
        print(f"  skill isolation: {'pass' if skill_check['passed'] else 'FAIL'}")
        print(f"  sandbox: {'pass' if sandbox_check['passed'] else 'FAIL'}")
        return 0
    if not args.yes and input("  this uses model quota. proceed? [y/N] ").strip().lower() != "y":
        print("  aborted")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = args.out / f"{stamp}-{args.suite}"
    run_dir.mkdir(parents=True, exist_ok=False)
    jobs = [(arm, rep, task) for rep in range(args.n) for task in tasks for arm in args.arms]
    random.Random(args.seed).shuffle(jobs)

    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="sarathi-repo-bench-") as temporary:
        temp_root = Path(temporary)
        _codex_home, codex_env = prepare_isolated_codex_home(temp_root)
        skill_preflight = skill_isolation_preflight(temp_root, codex_env)
        preflight = sandbox_preflight(temp_root, args.grader_timeout, codex_env)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {}
            for index, (arm, rep, task) in enumerate(jobs):
                workspace = temp_root / f"{index:04d}-{task.task_id}-{arm}-{rep}"
                future = pool.submit(
                    run_one, task, arm, arm_texts[arm], rep, args.model, args.effort,
                    args.agent_timeout, args.grader_timeout, workspace, codex_env,
                )
                futures[future] = (arm, rep, task, workspace)
            for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
                arm, rep, task, workspace = futures[future]
                result = future.result()
                if result.status != "infrastructure-invalid" and workspace.is_dir():
                    result.candidate_manifest = tree_manifest(workspace)
                    snapshot = run_dir / "candidates" / f"{task.task_id}-{arm}-rep{rep + 1}"
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(workspace, snapshot)
                    result.candidate_snapshot = str(snapshot.relative_to(run_dir))
                results.append(result)
                print(f"  [{number:>2}/{total_calls}] {arm} {task.task_id:<28} {result.status}")

    order = {arm: index for index, arm in enumerate(args.arms)}
    results.sort(key=lambda item: (order[item.arm], item.rep, item.task_id))
    task_manifest = {
        task.task_id: {
            "prompt": file_record(task.directory / "prompt.txt"),
            "starter": tree_manifest(task.starter),
            "hidden_test": file_record(task.hidden_test),
        }
        for task in tasks
    }
    manifest = {
        "runner": file_record(Path(__file__)),
        "skill": file_record(ROOT / "skills/sarathi/SKILL.md"),
        "competitors": file_record(ROOT / "bench/vendor/provenance.json"),
        "arms": {arm: {"sha256": sha256_bytes(text.encode()), "bytes": len(text.encode())} for arm, text in arm_texts.items()},
        "tasks": task_manifest,
    }
    metadata = {
        "timestamp": stamp,
        "suite": args.suite,
        "model": args.model,
        "effort": args.effort,
        "codex_version": subprocess.run(["codex", "--version"], capture_output=True, text=True).stdout.strip(),
        "python": sys.version,
        "platform": sys.platform,
        "arms": args.arms,
        "repetitions": args.n,
        "seed": args.seed,
        "pricing": pricing,
        "job_order": [{"arm": arm, "rep": rep, "task": task.task_id} for arm, rep, task in jobs],
        "sandbox": "Codex :workspace profile; network, repository writes, and home writes denied; temporary storage permitted",
        "sandbox_preflight": preflight,
        "skill_isolation_preflight": skill_preflight,
        "manifest": manifest,
        "infrastructure_invalid": sum(item.status == "infrastructure-invalid" for item in results),
    }
    (run_dir / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(
        json.dumps([dataclasses.asdict(item) for item in results], indent=2) + "\n",
        encoding="utf-8",
    )
    summary = summarize_results(results, args.arms, pricing)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report(results, args.arms, pricing)
    print(f"\n  local artifact: {run_dir}\n")
    return 1 if metadata["infrastructure_invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
