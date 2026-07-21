#!/usr/bin/env python3
"""Pointer-fidelity probe. The experiment that can falsify this project.

Arm C replaces a paragraph with a reference like `BG 2.47`. That only works if
the model resolves the reference to the right principle, and resolves it the
SAME way every time. If resolution is unreliable, the compression is fake: the
tokens are smaller but the instruction did not arrive.

This measures two things per anchor:

  accuracy    does the resolution contain the concepts the verse actually
              carries? Scored against expected/forbidden keyword sets, which is
              deterministic - no LLM judge, no second model to disagree with.

  consistency does it resolve the same way across n runs? A reference that means
              something different each time is not a pointer, it is noise.

A low score here explains any arm-C underperformance and is the single most
informative number in the study. Run it before believing any compression result.

Usage:
    python bench/fidelity.py --n 5
    python bench/fidelity.py --n 5 --anchor drift-cascade
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Deterministic scoring. `expect` are concepts the verse genuinely carries;
# `forbid` are plausible-but-wrong resolutions that indicate the model reached
# for a different verse or a generic platitude.
PROBES = {
    "action-not-fruit": {
        "expect": [r"action", r"fruit|result|outcome|reward"],
        "forbid": [r"inaction is always|never act|do not act at all"],
    },
    "steadiness": {
        "expect": [r"equanim|even|steady|balanc", r"success|failure"],
        "forbid": [r"indifferen(t|ce) to (the )?work|stop caring"],
    },
    "drift-cascade": {
        "expect": [r"attach|dwell|conte?mplat", r"anger|krodh", r"memory|smriti|smṛti", r"intellect|discrimina|buddhi|reason"],
        "forbid": [r"^.{0,200}$"],  # a real resolution of a 2-verse cascade is not 200 chars
    },
    "own-task": {
        "expect": [r"own (duty|dharma)|sva.?dharma", r"another|other'?s|para.?dharma"],
        "forbid": [r"caste is|birth determines"],
    },
    "inaction-is-action": {
        "expect": [r"action", r"inaction"],
        "forbid": [],
    },
    "effort-budget": {
        "expect": [r"too much|excess", r"too little|not enough|abstain", r"moderat|balanc"],
        "forbid": [],
    },
    "skill-in-action": {
        "expect": [r"skill", r"action|work"],
        "forbid": [],
    },
    "not-sole-cause": {
        "expect": [r"sole|only|alone", r"doer|agent|actor"],
        "forbid": [],
    },
    "release-the-decision": {
        "expect": [r"as you (wish|will|choose|desire)|do what you", r"reflect|conside|deliberat"],
        "forbid": [r"you must obey|therefore obey|surrender your judgment"],
    },
}

PROMPT = (
    "In one short paragraph: what does Bhagavad Gita {ref} say, "
    "and what single practical principle does it encode? "
    "If you are not certain of the verse, say so plainly."
)


def load_anchors() -> list[dict]:
    path = ROOT / "reference/anchors.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["anchors"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: cannot load anchors.json: {exc}", file=sys.stderr)
        raise SystemExit(1)


def ask(prompt: str, timeout: int) -> str | None:
    """One headless query. Returns None on failure rather than raising."""
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return proc.stdout
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        print("error: `claude` CLI not found on PATH", file=sys.stderr)
        raise SystemExit(1)


def score_accuracy(anchor_id: str, text: str) -> float:
    """Fraction of expected concepts present, zeroed if a forbidden pattern hits."""
    probe = PROBES.get(anchor_id)
    if not probe:
        return float("nan")

    for pattern in probe["forbid"]:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return 0.0

    expect = probe["expect"]
    if not expect:
        return float("nan")
    hits = sum(1 for p in expect if re.search(p, text, re.IGNORECASE))
    return hits / len(expect)


def jaccard(a: str, b: str) -> float:
    """Token-set overlap. Crude, but deterministic and dependency-free."""
    wa = set(re.findall(r"[a-z]{4,}", a.lower()))
    wb = set(re.findall(r"[a-z]{4,}", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def consistency(samples: list[str]) -> float:
    """Mean pairwise overlap across runs."""
    pairs = [
        jaccard(samples[i], samples[j])
        for i in range(len(samples))
        for j in range(i + 1, len(samples))
    ]
    return statistics.fmean(pairs) if pairs else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure whether verse pointers resolve reliably.")
    parser.add_argument("--n", type=int, default=5, help="samples per anchor (default 5)")
    parser.add_argument("--anchor", help="probe a single anchor by id")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--jobs", type=int, default=3, help="concurrent calls (default 3)")
    parser.add_argument("--out", type=Path, default=ROOT / "results/fidelity.json")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not shutil.which("claude"):
        print("error: `claude` CLI not found on PATH", file=sys.stderr)
        return 1

    anchors = load_anchors()
    if args.anchor:
        anchors = [a for a in anchors if a["id"] == args.anchor]
        if not anchors:
            print(f"error: no anchor with id {args.anchor!r}", file=sys.stderr)
            return 1

    total = len(anchors) * args.n
    print(f"\n  {len(anchors)} anchors × {args.n} samples = {total} API calls")
    if not args.yes:
        if input("  this costs real money. proceed? [y/N] ").strip().lower() != "y":
            print("  aborted")
            return 0

    jobs = [(anchor, i) for anchor in anchors for i in range(args.n)]

    def execute(job):
        anchor, _ = job
        return anchor["id"], ask(PROMPT.format(ref=anchor["refs"][0]), args.timeout)

    print()
    collected: dict[str, list[str]] = {a["id"]: [] for a in anchors}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for anchor_id, out in pool.map(execute, jobs):
            done += 1
            if out:
                collected[anchor_id].append(out)
            print(f"  [{done:>3}/{len(jobs)}] {anchor_id}", end="\r", flush=True)
    print(" " * 60, end="\r")

    results = []
    for anchor in anchors:
        ref = anchor["refs"][0]
        samples = collected[anchor["id"]]

        if not samples:
            print(f"  {anchor['id']:<24} no samples returned")
            continue

        accuracies = [score_accuracy(anchor["id"], s) for s in samples]
        valid = [a for a in accuracies if a == a]
        acc = statistics.fmean(valid) if valid else float("nan")
        cons = consistency(samples)

        results.append({
            "id": anchor["id"],
            "ref": ref,
            "n": len(samples),
            "accuracy": acc,
            "consistency": cons,
            "samples": samples,
        })

        flag = "  <-- pointer unreliable" if (acc == acc and acc < 0.7) else ""
        print(f"  {anchor['id']:<24} {ref:<10} acc {acc:5.2f}   consistency {cons:5.2f}{flag}")

    if results:
        accs = [r["accuracy"] for r in results if r["accuracy"] == r["accuracy"]]
        conss = [r["consistency"] for r in results if r["consistency"] == r["consistency"]]
        print("  " + "─" * 66)
        if accs:
            print(f"  mean accuracy    {statistics.fmean(accs):.2f}")
        if conss:
            print(f"  mean consistency {statistics.fmean(conss):.2f}")
        weak = [r["id"] for r in results if r["accuracy"] == r["accuracy"] and r["accuracy"] < 0.7]
        if weak:
            print(f"\n  unreliable pointers: {', '.join(weak)}")
            print("  these anchors should be dropped or replaced with plain text.")
        else:
            print("\n  all pointers resolved above threshold.")

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  raw: {args.out}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
