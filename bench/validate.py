#!/usr/bin/env python3
"""Repo invariant checks for sarathi.

Enforces the integrity rules the README claims, so the project cannot quietly
drift away from its own argument. Run in CI and before any release.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Description is loaded into context every session for routing; body loads on
# demand. So the description is the number that actually needs a hard budget.
DESCRIPTION_BUDGET = 400
BODY_BUDGET = 4000

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _skill_path() -> Path:
    return ROOT / "skills/sarathi/SKILL.md"


def check_json_parses() -> list[str]:
    errors = []
    targets = [ROOT / ".claude-plugin/plugin.json", ROOT / "reference/anchors.json"]
    targets += sorted((ROOT / "bench/tasks").glob("*.json"))
    for path in targets:
        if not path.exists():
            errors.append(f"{path.relative_to(ROOT)}: missing")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def check_every_verse_has_a_source() -> list[str]:
    """No Sanskrit may enter the repo without a recorded origin.

    The project's whole mechanism is that a reference resolves to the right
    text. Citation hallucination runs 13-21% even under retrieval grounding, so
    hand-typed verses are the one thing that cannot be allowed.
    """
    path = ROOT / "reference/anchors.json"
    if not path.exists():
        return ["reference/anchors.json missing — run bench/build_anchors.py"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"anchors.json: {exc}"]

    errors = []
    for anchor in data.get("anchors", []):
        if not anchor.get("verses"):
            errors.append(f"{anchor.get('id', '?')}: no verses")
        for verse in anchor.get("verses", []):
            if not verse.get("source"):
                errors.append(f"{verse.get('ref', '?')}: no source recorded")
            if not verse.get("devanagari") or not verse.get("iast"):
                errors.append(f"{verse.get('ref', '?')}: missing text")
    return errors


def check_no_chapter_13() -> list[str]:
    """Chapter 13 has 34 or 35 verses depending on recension.

    A `BG 13.x` pointer is therefore ambiguous, and an ambiguous pointer is
    exactly the failure this project exists to measure.
    """
    path = ROOT / "reference/anchors.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        f"{v['ref']} — chapter 13 is recension-ambiguous (34 vs 35 verses)"
        for a in data.get("anchors", [])
        for v in a.get("verses", [])
        if v.get("chapter") == 13
    ]


def check_every_anchor_maps_to_a_failure_mode() -> list[str]:
    """An anchor without a documented failure mode is decoration."""
    path = ROOT / "reference/anchors.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for anchor in data.get("anchors", []):
        if not anchor.get("failure_mode"):
            errors.append(f"{anchor.get('id', '?')}: no failure_mode")
        if not anchor.get("evidence"):
            errors.append(f"{anchor.get('id', '?')}: no evidence for the failure mode")
        if not anchor.get("operational") or not anchor.get("literal"):
            errors.append(f"{anchor.get('id', '?')}: literal and operational must both be present")
    return errors


def check_no_devanagari_in_hot_path() -> list[str]:
    """Devanagari costs 2-4 tokens per character (arXiv 2601.06142).

    Inlining it would destroy the saving the project claims. Script belongs in
    reference/, which loads on demand.
    """
    errors = []
    for path in [_skill_path(), *sorted((ROOT / "bench/arms").glob("*.txt"))]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if DEVANAGARI.search(text):
            errors.append(f"{path.relative_to(ROOT)}: contains Devanagari — belongs in reference/")
    return errors


def check_skill_budget() -> list[str]:
    path = _skill_path()
    if not path.exists():
        return ["skills/sarathi/SKILL.md missing"]
    text = path.read_text(encoding="utf-8")

    errors = []
    if not text.startswith("---"):
        return ["SKILL.md: no frontmatter"]
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ["SKILL.md: unterminated frontmatter"]

    head, body = parts[1], parts[2]
    for field in ("name:", "description:"):
        if field not in head:
            errors.append(f"SKILL.md: missing {field}")

    desc_lines = [l for l in head.splitlines() if l.startswith("description:")]
    if desc_lines and len(desc_lines[0]) > DESCRIPTION_BUDGET:
        errors.append(
            f"SKILL.md: description {len(desc_lines[0])} chars > {DESCRIPTION_BUDGET} "
            "(loaded every session, keep it tight)"
        )
    if len(body) > BODY_BUDGET:
        errors.append(f"SKILL.md: body {len(body)} chars > {BODY_BUDGET}")
    return errors


def check_arms_differ_only_in_encoding() -> list[str]:
    """Arms B and C must come from the same anchors, or the experiment is invalid.

    If B mentions a principle C omits, a difference in result could be content
    rather than encoding - which is the one confound this design exists to avoid.
    """
    arms = ROOT / "bench/arms"
    anchors_path = ROOT / "reference/anchors.json"
    if not (arms / "B.txt").exists() or not (arms / "C.txt").exists():
        return ["bench/arms not built — run bench/build_arms.py"]
    if not anchors_path.exists():
        return []

    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    ids = [a["id"] for a in data.get("anchors", [])]
    c_text = (arms / "C.txt").read_text(encoding="utf-8")

    errors = []
    for anchor_id in ids:
        if anchor_id not in c_text:
            errors.append(f"arm C missing anchor {anchor_id}")

    b_text = (arms / "B.txt").read_text(encoding="utf-8")
    if DEVANAGARI.search(b_text) or re.search(r"\bBG \d", b_text):
        errors.append("arm B contains verse references — B must be reference-free to isolate the variable")
    return errors


def check_ablation_arms() -> list[str]:
    """Arms D and E are the controls that make the result defensible.

    D must carry only wrong references (else it is a second copy of C), and E
    must carry none (else it does not isolate the label).
    """
    arms = ROOT / "bench/arms"
    anchors_path = ROOT / "reference/anchors.json"
    if not anchors_path.exists():
        return []

    errors = []
    for name in ("D", "E"):
        if not (arms / f"{name}.txt").exists():
            errors.append(f"arm {name} not built — run bench/build_arms.py")
    if errors:
        return errors

    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    correct = {ref for a in data["anchors"] for ref in a["refs"]}

    d_text = (arms / "D.txt").read_text(encoding="utf-8")
    d_refs = set(re.findall(r"BG \d+\.\d+", d_text))
    overlap = d_refs & correct
    if overlap:
        errors.append(f"arm D contains correct references {sorted(overlap)} — the control is poisoned")
    if not d_refs:
        errors.append("arm D has no references at all")
    if any(r.startswith("BG 13.") for r in d_refs):
        errors.append("arm D uses chapter 13, which is recension-ambiguous")

    e_text = (arms / "E.txt").read_text(encoding="utf-8")
    if re.search(r"\bBG \d", e_text):
        errors.append("arm E contains references — it must isolate the label alone")

    # C and D must cost the same, or the comparison measures length not correctness.
    c_len = len((arms / "C.txt").read_text(encoding="utf-8"))
    d_len = len(d_text)
    if c_len and abs(c_len - d_len) / c_len > 0.05:
        errors.append(f"arms C ({c_len}) and D ({d_len}) differ by >5% in length — confounds the ablation")

    return errors


def check_fidelity_probes_cover_anchors() -> list[str]:
    """Every anchor needs a probe, or its reliability is untested."""
    anchors_path = ROOT / "reference/anchors.json"
    probe_path = ROOT / "bench/fidelity.py"
    if not anchors_path.exists() or not probe_path.exists():
        return []
    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    probes = probe_path.read_text(encoding="utf-8")
    return [
        f"{a['id']}: no fidelity probe — its pointer reliability is unmeasured"
        for a in data.get("anchors", [])
        if f'"{a["id"]}"' not in probes
    ]


CHECKS = [
    ("json parses", check_json_parses),
    ("every verse has a source", check_every_verse_has_a_source),
    ("no chapter-13 anchors", check_no_chapter_13),
    ("anchors map to failure modes", check_every_anchor_maps_to_a_failure_mode),
    ("no devanagari in hot path", check_no_devanagari_in_hot_path),
    ("skill within budget", check_skill_budget),
    ("arms differ only in encoding", check_arms_differ_only_in_encoding),
    ("ablation arms are valid controls", check_ablation_arms),
    ("fidelity probes cover anchors", check_fidelity_probes_cover_anchors),
]


def main() -> int:
    failed = False
    for label, check in CHECKS:
        errors = check()
        if errors:
            failed = True
            print(f"  FAIL  {label}")
            for e in errors:
                print(f"        {e}")
        else:
            print(f"  ok    {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
