#!/usr/bin/env python3
"""Post-hoc diagnostic rescore for a saved benchmark artifact.

This never overwrites original labels. Output is explicitly non-confirmatory
because changing a rubric after seeing answers can bias a result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze
import run

ROOT = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rescore_rows(rows: list[dict], tasks: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    rescored = []
    changes = []
    for row in rows:
        updated = dict(row)
        passed, violations = run.score(tasks[row["task_id"]], row["output"])
        updated["passed"] = passed
        updated["violations"] = violations
        rescored.append(updated)
        if passed != row["passed"] or violations != row["violations"]:
            changes.append({
                "arm": row["arm"],
                "task_id": row["task_id"],
                "rep": row["rep"],
                "old_passed": row["passed"],
                "new_passed": passed,
                "old_violations": row["violations"],
                "new_violations": violations,
            })
    return rescored, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostically rescore a saved run")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    meta_path = run_dir / "meta.json"
    results_path = run_dir / "results.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    rows = json.loads(results_path.read_text(encoding="utf-8"))
    task_list = run.load_tasks(meta["tasks"])
    tasks = {task["id"]: task for task in task_list}
    rescored, changes = rescore_rows(rows, tasks)

    task_hashes = {
        name: digest(ROOT / f"bench/tasks/{name}.json")
        for name in meta["tasks"]
    }
    artifact = {
        "schema_version": 1,
        "status": "post-hoc diagnostic, not confirmatory evidence",
        "source": {
            "run_dir": str(run_dir.relative_to(ROOT)) if run_dir.is_relative_to(ROOT) else str(run_dir),
            "meta_sha256": digest(meta_path),
            "results_sha256": digest(results_path),
            "original_scorer_sha256": meta.get("manifest", {}).get("scorer", {}).get("sha256"),
        },
        "rescore": {
            "current_scorer_sha256": digest(ROOT / "bench/run.py"),
            "current_task_sha256": task_hashes,
            "changed_rows": changes,
        },
        "summary": analyze.clean_numbers(analyze.summarize(rescored, meta["arms"])),
    }
    path = run_dir / "posthoc-rescore.json"
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
