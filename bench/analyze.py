#!/usr/bin/env python3
"""Analyze one benchmark artifact without making model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

import net
import build_arms
import stats

ROOT = Path(__file__).resolve().parent.parent


def cost_per_pass_ci(rows: list[dict], iterations: int = 10_000, seed: int = 0) -> tuple[float, float]:
    """Bootstrap total call cost divided by successful calls."""
    if (
        len(rows) < 2
        or not any(row["passed"] for row in rows)
        or any("cost_usd" not in row["usage"] for row in rows)
    ):
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        passed = sum(row["passed"] for row in sample)
        if passed:
            estimates.append(sum(row["usage"]["cost_usd"] for row in sample) / passed)
    estimates.sort()
    if not estimates:
        return (float("nan"), float("nan"))
    return (
        estimates[int(0.025 * len(estimates))],
        estimates[min(int(0.975 * len(estimates)), len(estimates) - 1)],
    )


def summarize(rows: list[dict], arms: list[str]) -> dict:
    out = {"arms": {}, "comparisons": {}}
    counts = {}
    for arm in arms:
        subset = [row for row in rows if row["arm"] == arm and row.get("usage")]
        passed = sum(bool(row["passed"]) for row in subset)
        n = len(subset)
        costs = [float(row["usage"]["cost_usd"]) for row in subset if "cost_usd" in row["usage"]]
        outputs = [float(row["usage"]["output_tokens"]) for row in subset]
        total_tokens = [
            float(row["usage"].get("input_tokens", 0))
            + float(row["usage"].get("cache_creation_input_tokens", 0))
            + float(row["usage"].get("cache_read_input_tokens", 0))
            + float(row["usage"].get("output_tokens", 0))
            for row in subset
        ]
        durations = [float(row["usage"].get("duration_ms", 0)) for row in subset]
        rate = passed / n if n else None
        has_cost = len(costs) == n and n > 0
        cost_per_pass = sum(costs) / passed if has_cost and passed else None
        tokens_per_pass = sum(total_tokens) / passed if passed else None
        counts[arm] = (passed, n)
        out["arms"][arm] = {
            "n": n,
            "passed": passed,
            "pass_rate": rate,
            "pass_rate_wilson_95": list(stats.wilson(passed, n)),
            "output_tokens_mean": statistics.fmean(outputs) if outputs else None,
            "output_tokens_bootstrap_95": list(net.bootstrap_ci(outputs)),
            "total_tokens_mean": statistics.fmean(total_tokens) if total_tokens else None,
            "tokens_per_pass": tokens_per_pass,
            "cost_per_call_mean": statistics.fmean(costs) if has_cost else None,
            "cost_per_call_bootstrap_95": list(net.bootstrap_ci(costs)) if has_cost else [None, None],
            "cost_per_pass": cost_per_pass,
            "cost_per_pass_bootstrap_95": list(cost_per_pass_ci(subset)),
            "duration_ms_mean": statistics.fmean(durations) if durations else None,
            "total_cost": sum(costs) if has_cost else None,
        }

    control = counts.get("A")
    if control:
        for arm, (passed, n) in counts.items():
            if arm == "A" or not n:
                continue
            ci = stats.newcombe(passed, n, control[0], control[1])
            delta = passed / n - control[0] / control[1]
            out["comparisons"][f"{arm}_vs_A"] = {
                "pass_rate_delta": delta,
                "newcombe_95": list(ci),
                "significant": stats.significant(ci),
            }
    arm_costs = [item["total_cost"] for item in out["arms"].values()]
    out["total_cost"] = sum(arm_costs) if arm_costs and all(cost is not None for cost in arm_costs) else None
    return out


def verify_manifest(meta: dict) -> dict:
    manifest = meta.get("manifest")
    if not manifest:
        return {"recorded": False, "matches": False, "errors": ["artifact has no manifest"]}
    errors = []
    records = []
    for value in manifest.values():
        if isinstance(value, dict) and "path" in value:
            records.append(value)
        elif isinstance(value, dict):
            records.extend(record for record in value.values() if isinstance(record, dict) and "path" in record)
    for record in records:
        path = ROOT / record["path"]
        if not path.is_file():
            errors.append(f"missing: {record['path']}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != record["sha256"]:
            errors.append(f"changed: {record['path']}")
    try:
        current_arms = build_arms.build_all()
    except (RuntimeError, SystemExit) as exc:
        errors.append(f"cannot rebuild arms: {exc}")
        current_arms = {}
    for arm, record in manifest.get("arms", {}).items():
        if "arm" not in record:
            continue
        content = current_arms.get(arm)
        if content is None:
            errors.append(f"missing generated arm: {arm}")
            continue
        data = content.encode("utf-8")
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            errors.append(f"changed generated arm: {arm}")
        if len(data) != record.get("bytes"):
            errors.append(f"changed generated arm size: {arm}")
    return {"recorded": True, "matches": not errors, "errors": errors}


def clean_numbers(value):
    """Replace JSON-invalid NaN values with null recursively."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: clean_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_numbers(item) for item in value]
    return value


def analyze(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    rows = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    return clean_numbers({
        "schema_version": 1,
        "run": str(run_dir.relative_to(ROOT)) if run_dir.is_relative_to(ROOT) else str(run_dir),
        "metadata": meta,
        "manifest_verification": verify_manifest(meta),
        **summarize(rows, meta["arms"]),
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a benchmark artifact")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--write", action="store_true", help="write summary.json beside raw files")
    args = parser.parse_args()
    result = analyze(args.run_dir.resolve())
    rendered = json.dumps(result, indent=2) + "\n"
    if args.write:
        (args.run_dir / "summary.json").write_text(rendered, encoding="utf-8")
        print(args.run_dir / "summary.json")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
