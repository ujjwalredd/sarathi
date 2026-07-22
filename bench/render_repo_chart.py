#!/usr/bin/env python3
"""Render a static, accessible SVG from a repository benchmark summary."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ORDER = ["A", "F", "G", "H"]
COLORS = {
    "A": "#64748b",
    "F": "#0f766e",
    "G": "#2563eb",
    "H": "#d97706",
}


def number(value: float | None, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "percent":
        return f"{value:.0%}"
    if kind == "usd":
        return f"${value:.3f}"
    if kind == "seconds":
        return f"{value / 1000:.1f}s"
    return f"{value:,.0f}"


def chart(summary: dict, metadata: dict) -> str:
    arms = summary["arms"]
    rows = [arm for arm in ORDER if arm in arms]
    calls = sum(arms[arm]["valid"] + arms[arm]["infrastructure_invalid"] for arm in rows)
    title = "Executable repository benchmark"
    subtitle = (
        f"{metadata.get('model', 'model unknown')}, {metadata.get('effort', 'effort unknown')} effort, "
        f"{calls} calls. Correctness is higher-better; cost, tokens, and time are lower-better."
    )
    metrics = [
        ("Verified pass rate", "pass_rate", "percent"),
        (
            "API-equivalent cost per verified pass",
            "estimated_api_cost_per_verified_pass_usd",
            "usd",
        ),
        ("Raw tokens per verified pass", "raw_tokens_per_verified_pass", "tokens"),
        ("Mean agent time", "mean_duration_ms", "seconds"),
    ]

    width, height = 1200, 720
    panel_width, panel_height = 540, 250
    positions = [(60, 130), (660, 130), (60, 430), (660, 430)]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="chart-title chart-desc">',
        f"<title id=\"chart-title\">{html.escape(title)}</title>",
        f"<desc id=\"chart-desc\">{html.escape(subtitle)}</desc>",
        """<style>
          .heading { fill: #0f172a; font: 500 28px system-ui, sans-serif; }
          .subheading { fill: #475569; font: 400 16px system-ui, sans-serif; }
          .panel-title { fill: #0f172a; font: 500 17px system-ui, sans-serif; }
          .label { fill: #334155; font: 500 14px system-ui, sans-serif; }
          .value { fill: #0f172a; font: 500 14px ui-monospace, monospace; }
          .track { fill: #e2e8f0; }
          @media (prefers-color-scheme: dark) {
            .heading, .panel-title, .value { fill: #f8fafc; }
            .subheading, .label { fill: #cbd5e1; }
            .track { fill: #334155; }
          }
        </style>""",
        f'<text class="heading" x="60" y="52">{html.escape(title)}</text>',
        f'<text class="subheading" x="60" y="82">{html.escape(subtitle)}</text>',
    ]

    for (metric_title, field, kind), (x, y) in zip(metrics, positions):
        values = [arms[arm].get(field) for arm in rows]
        maximum = max((value for value in values if value is not None), default=1) or 1
        parts.append(f'<text class="panel-title" x="{x}" y="{y}">{html.escape(metric_title)}</text>')
        for index, arm in enumerate(rows):
            item = arms[arm]
            value = item.get(field)
            row_y = y + 38 + index * 46
            bar_x = x + 105
            bar_width = 340
            fill_width = 0 if value is None else max(value / maximum * bar_width, 2)
            label = item["label"]
            parts.extend(
                [
                    f'<text class="label" x="{x}" y="{row_y + 15}">{html.escape(label)}</text>',
                    f'<rect class="track" x="{bar_x}" y="{row_y}" width="{bar_width}" height="20" rx="3"/>',
                    f'<rect x="{bar_x}" y="{row_y}" width="{fill_width:.1f}" height="20" rx="3" fill="{COLORS[arm]}"/>',
                    f'<text class="value" x="{x + panel_width}" y="{row_y + 15}" text-anchor="end">{html.escape(number(value, kind))}</text>',
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("assets/repo-benchmark.svg"))
    args = parser.parse_args()
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((args.run_dir / "meta.json").read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(chart(summary, metadata), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
