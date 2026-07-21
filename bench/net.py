#!/usr/bin/env python3
"""Net token accounting for Claude Code sessions.

Every skill in the token-efficiency category reports gross output savings. None
subtract what the skill itself costs to carry. This computes the net.

The distinction that matters is *where* a skill's text lands:

  - Text in the system prompt or a SessionStart block enters the cached prefix.
    It is billed once at the cache-write rate, then at the cache-read rate for
    every turn after. Cache reads are ~10x cheaper than fresh input.

  - Text injected per-turn (a UserPromptSubmit hook) lands after the cached
    prefix. It is billed at the full input rate on every single turn, forever.

A skill that saves 60% of output tokens while re-injecting a reminder on every
turn is not obviously a win, and no README in this category reports the number
that would settle it.

Costs are reported in normalized units rather than dollars by default, so the
result does not depend on a price table going stale. One unit = one fresh input
token. Pass --price-in/--price-out for dollar figures.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

# Ratios relative to a fresh input token. These are stable across Anthropic's
# pricing tiers, which is why the default report is ratio-based: a price table
# goes out of date, the ratios do not.
OUTPUT_RATIO = 5.0
CACHE_WRITE_RATIO = 1.25
CACHE_READ_RATIO = 0.1


@dataclass
class Usage:
    """Token counts for a single assistant turn."""

    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            self.cache_read_input_tokens + other.cache_read_input_tokens,
            self.output_tokens + other.output_tokens,
        )

    def cost_units(self) -> float:
        """Normalized cost. One unit = one fresh input token."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens * CACHE_WRITE_RATIO
            + self.cache_read_input_tokens * CACHE_READ_RATIO
            + self.output_tokens * OUTPUT_RATIO
        )

    def dollars(self, price_in: float, price_out: float) -> float:
        """Cost in dollars given per-million-token input and output prices."""
        per_token_in = price_in / 1_000_000
        per_token_out = price_out / 1_000_000
        return (
            self.input_tokens * per_token_in
            + self.cache_creation_input_tokens * per_token_in * CACHE_WRITE_RATIO
            + self.cache_read_input_tokens * per_token_in * CACHE_READ_RATIO
            + self.output_tokens * per_token_out
        )


@dataclass
class Session:
    """One Claude Code session, aggregated."""

    session_id: str
    path: Path
    models: set[str] = field(default_factory=set)
    turns: int = 0
    usage: Usage = field(default_factory=Usage)

    @property
    def model(self) -> str:
        # Sessions can span a model switch. Report all of them rather than
        # silently picking one - a benchmark that mixes models is invalid and
        # the reader needs to see that.
        return ",".join(sorted(self.models)) if self.models else "unknown"


def _iter_records(path: Path) -> Iterator[dict]:
    """Yield parsed JSON records, skipping malformed lines.

    Session logs are appended live and can be truncated mid-write if a session
    is still running, so a trailing partial line is expected rather than
    exceptional.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"warning: {path.name}:{lineno} malformed, skipped",
                        file=sys.stderr,
                    )
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)


def parse_session(path: Path) -> Session | None:
    """Aggregate one session log. Returns None if it holds no billable turns."""
    session = Session(session_id=path.stem, path=path)

    for record in _iter_records(path):
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue

        model = message.get("model")
        if model:
            session.models.add(model)

        session.turns += 1
        session.usage += Usage(
            input_tokens=usage.get("input_tokens", 0) or 0,
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0) or 0,
            output_tokens=usage.get("output_tokens", 0) or 0,
        )

    return session if session.turns else None


def load_sessions(paths: Iterable[Path]) -> list[Session]:
    """Load sessions from files or directories of .jsonl files."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.jsonl")))
        elif path.is_file():
            files.append(path)
        else:
            print(f"warning: no such path: {path}", file=sys.stderr)

    sessions = [s for s in (parse_session(f) for f in files) if s is not None]
    return sessions


def bootstrap_ci(
    values: Sequence[float],
    confidence: float = 0.95,
    iterations: int = 10_000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean.

    Non-parametric because per-task cost is heavily right-skewed - one task that
    sends the agent down a rabbit hole dominates the sample, and assuming
    normality would understate the interval.
    """
    if len(values) < 2:
        return (float("nan"), float("nan"))

    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))
    means.sort()

    tail = (1.0 - confidence) / 2.0
    lo = means[int(tail * iterations)]
    hi = means[min(int((1.0 - tail) * iterations), iterations - 1)]
    return (lo, hi)


def _pct(new: float, old: float) -> float:
    """Percentage change from old to new. NaN when old is zero."""
    if old == 0:
        return float("nan")
    return (new - old) / old * 100.0


def _fmt_pct(value: float) -> str:
    if value != value:  # NaN
        return "    n/a"
    return f"{value:+6.1f}%"


def summarize(label: str, sessions: Sequence[Session]) -> dict:
    total = Usage()
    for s in sessions:
        total += s.usage
    turns = sum(s.turns for s in sessions)
    models = sorted({m for s in sessions for m in s.models})
    return {
        "label": label,
        "sessions": len(sessions),
        "turns": turns,
        "usage": total,
        "models": models,
        "per_session_units": [s.usage.cost_units() for s in sessions],
    }


def compare(baseline: dict, treatment: dict, price_in: float | None, price_out: float | None) -> str:
    b: Usage = baseline["usage"]
    t: Usage = treatment["usage"]

    lines: list[str] = []
    add = lines.append

    add("")
    add(f"  {treatment['label']}  vs  {baseline['label']}")
    add("  " + "─" * 68)
    add(
        f"  sessions {baseline['sessions']:>4} → {treatment['sessions']:<4}"
        f"     turns {baseline['turns']:>5} → {treatment['turns']:<5}"
    )

    b_models = ",".join(baseline["models"]) or "unknown"
    t_models = ",".join(treatment["models"]) or "unknown"
    add(f"  model    {b_models} → {t_models}")
    if b_models != t_models:
        add("  ⚠  models differ between arms — this comparison is not valid")
    add("  " + "─" * 68)

    add("  output tokens        "
        f"{b.output_tokens:>10,} → {t.output_tokens:>10,}   {_fmt_pct(_pct(t.output_tokens, b.output_tokens))}")
    add("     ↑ the number every other README reports")
    add("")
    add("  input, fresh         "
        f"{b.input_tokens:>10,} → {t.input_tokens:>10,}   {_fmt_pct(_pct(t.input_tokens, b.input_tokens))}")
    add("  input, cache write   "
        f"{b.cache_creation_input_tokens:>10,} → {t.cache_creation_input_tokens:>10,}   "
        f"{_fmt_pct(_pct(t.cache_creation_input_tokens, b.cache_creation_input_tokens))}")
    add("  input, cache read    "
        f"{b.cache_read_input_tokens:>10,} → {t.cache_read_input_tokens:>10,}   "
        f"{_fmt_pct(_pct(t.cache_read_input_tokens, b.cache_read_input_tokens))}")
    add("     ↑ fresh input is the expensive tier. A per-turn hook lands here.")
    add("        A SessionStart block lands in cache read, ~10x cheaper.")
    add("  " + "─" * 68)

    b_units, t_units = b.cost_units(), t.cost_units()
    add(f"  NET cost (units)     {b_units:>10,.0f} → {t_units:>10,.0f}   {_fmt_pct(_pct(t_units, b_units))}")

    if price_in is not None and price_out is not None:
        b_usd, t_usd = b.dollars(price_in, price_out), t.dollars(price_in, price_out)
        add(f"  NET cost (USD)       {b_usd:>10,.4f} → {t_usd:>10,.4f}   {_fmt_pct(_pct(t_usd, b_usd))}")

    # Per-session CI needs paired arms of equal length to be meaningful.
    b_vals = baseline["per_session_units"]
    t_vals = treatment["per_session_units"]
    if len(b_vals) == len(t_vals) and len(b_vals) >= 2:
        deltas = [_pct(tv, bv) for tv, bv in zip(t_vals, b_vals) if bv > 0]
        if len(deltas) >= 2:
            lo, hi = bootstrap_ci(deltas)
            mean = statistics.fmean(deltas)
            add(f"  per-session mean     {mean:+.1f}%   95% CI [{lo:+.1f}%, {hi:+.1f}%]   n={len(deltas)}")
            if lo < 0 < hi:
                add("  ⚠  CI spans zero — this run does not show a real effect")
    elif len(b_vals) != len(t_vals):
        add("  note: arms differ in length; per-session CI omitted (needs paired runs)")
    else:
        add("  note: n < 2, no confidence interval")

    add("  " + "─" * 68)
    verdict = "net win" if t_units < b_units else "net loss"
    gross = _pct(t.output_tokens, b.output_tokens)
    net = _pct(t_units, b_units)
    add(f"  VERDICT: {verdict}. gross output {_fmt_pct(gross).strip()}, net {_fmt_pct(net).strip()}")
    if gross == gross and net == net and gross < 0 and net > gross:
        add(f"           the headline number overstates the saving by {abs(gross - net):.1f} points")
    add("")

    return "\n".join(lines)


def default_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="net.py",
        description="Net token accounting for Claude Code sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  net.py --baseline runs/baseline --treatment runs/loadbearing\n"
            "  net.py --scan                      # summarize all local sessions\n"
            "  net.py --baseline a --treatment b --price-in 5 --price-out 25\n"
        ),
    )
    parser.add_argument("--baseline", type=Path, nargs="+", help="session logs for the control arm")
    parser.add_argument("--treatment", type=Path, nargs="+", help="session logs for the skill arm")
    parser.add_argument("--scan", action="store_true", help="summarize all sessions under ~/.claude/projects")
    parser.add_argument("--price-in", type=float, help="USD per million input tokens")
    parser.add_argument("--price-out", type=float, help="USD per million output tokens")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    if (args.price_in is None) != (args.price_out is None):
        parser.error("--price-in and --price-out must be given together")

    if args.scan:
        sessions = load_sessions([default_projects_dir()])
        if not sessions:
            print("no sessions found", file=sys.stderr)
            return 1
        summary = summarize("all sessions", sessions)
        usage: Usage = summary["usage"]
        if args.json:
            print(json.dumps({
                "sessions": summary["sessions"],
                "turns": summary["turns"],
                "models": summary["models"],
                "input_tokens": usage.input_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens,
                "cache_read_input_tokens": usage.cache_read_input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_units": usage.cost_units(),
            }, indent=2))
        else:
            print(f"\n  {summary['sessions']} sessions, {summary['turns']} assistant turns")
            print(f"  models: {', '.join(summary['models']) or 'unknown'}")
            print(f"  input  fresh/write/read: {usage.input_tokens:,} / "
                  f"{usage.cache_creation_input_tokens:,} / {usage.cache_read_input_tokens:,}")
            print(f"  output: {usage.output_tokens:,}")
            print(f"  cost units: {usage.cost_units():,.0f}\n")
        return 0

    if not args.baseline or not args.treatment:
        parser.error("need --baseline and --treatment, or --scan")

    baseline_sessions = load_sessions(args.baseline)
    treatment_sessions = load_sessions(args.treatment)

    if not baseline_sessions:
        print("error: no billable turns in baseline arm", file=sys.stderr)
        return 1
    if not treatment_sessions:
        print("error: no billable turns in treatment arm", file=sys.stderr)
        return 1

    baseline = summarize("baseline", baseline_sessions)
    treatment = summarize("loadbearing", treatment_sessions)

    if args.json:
        def pack(s: dict) -> dict:
            u: Usage = s["usage"]
            return {
                "label": s["label"],
                "sessions": s["sessions"],
                "turns": s["turns"],
                "models": s["models"],
                "input_tokens": u.input_tokens,
                "cache_creation_input_tokens": u.cache_creation_input_tokens,
                "cache_read_input_tokens": u.cache_read_input_tokens,
                "output_tokens": u.output_tokens,
                "cost_units": u.cost_units(),
            }
        print(json.dumps({"baseline": pack(baseline), "treatment": pack(treatment)}, indent=2))
    else:
        print(compare(baseline, treatment, args.price_in, args.price_out))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
