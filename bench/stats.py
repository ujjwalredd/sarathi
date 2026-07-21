#!/usr/bin/env python3
"""Confidence intervals for pass-rate comparisons.

Binary outcomes at small n need intervals or the numbers mislead. A 12.5 point
gap on n=28 is indistinguishable from noise, and reporting it bare is how this
whole category of benchmark went wrong in the first place.

Wilson score intervals for single proportions, Newcombe's method for the
difference between two independent proportions. Both are standard, both behave
correctly near 0 and 1 where the normal approximation falls apart, and both are
computable from the stdlib.

Matches the method used in results/codex-skill/ so the two studies can be read
side by side.
"""

from __future__ import annotations

import math

# 1.959963985 = the 97.5th percentile of the standard normal.
Z95 = 1.959963984540054


def wilson(passed: int, total: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a single proportion.

    Preferred over the normal approximation because it does not produce
    impossible bounds below 0 or above 1, which matters here: several arms
    legitimately score 0% or 100% on a subset.
    """
    if total == 0:
        return (float("nan"), float("nan"))
    p = passed / total
    denom = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return ((centre - spread) / denom, (centre + spread) / denom)


def newcombe(passed_a: int, total_a: int, passed_b: int, total_b: int, z: float = Z95) -> tuple[float, float]:
    """Newcombe hybrid score interval for the difference p_a - p_b.

    Builds the difference interval from each arm's Wilson bounds rather than
    pooling variance, which keeps it honest at extreme proportions.
    """
    if total_a == 0 or total_b == 0:
        return (float("nan"), float("nan"))
    l1, u1 = wilson(passed_a, total_a, z)
    l2, u2 = wilson(passed_b, total_b, z)
    p1 = passed_a / total_a
    p2 = passed_b / total_b
    lower = (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (lower, upper)


def significant(ci: tuple[float, float]) -> bool:
    """True only when the interval excludes zero."""
    lo, hi = ci
    if lo != lo or hi != hi:  # NaN
        return False
    return lo > 0 or hi < 0


def required_n(p_control: float, effect: float, power: float = 0.80, z: float = Z95) -> int:
    """Rough per-arm n to detect `effect` at 95% confidence and given power.

    Normal-approximation sample size, adequate for planning a run rather than
    for reporting a result. Returned so a pilot can say what a real run costs
    instead of guessing.
    """
    if not 0 < p_control < 1 or effect <= 0:
        return 0
    p2 = min(max(p_control + effect, 1e-6), 1 - 1e-6)
    z_beta = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}.get(power, 0.8416)
    pbar = (p_control + p2) / 2
    numerator = (z * math.sqrt(2 * pbar * (1 - pbar)) + z_beta * math.sqrt(
        p_control * (1 - p_control) + p2 * (1 - p2)
    )) ** 2
    return math.ceil(numerator / effect**2)


def fmt_ci(ci: tuple[float, float]) -> str:
    lo, hi = ci
    if lo != lo or hi != hi:
        return "     n/a      "
    return f"[{lo * 100:+5.1f}, {hi * 100:+5.1f}]"
