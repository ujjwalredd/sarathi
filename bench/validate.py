#!/usr/bin/env python3
"""Repo invariant checks for sarathi.

Enforces the integrity rules the README claims, so the project cannot quietly
drift away from its own argument. Run in CI and before any release.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import sys
from pathlib import Path

import build_arms

ROOT = Path(__file__).resolve().parent.parent

# Description is loaded into context every session for routing; body loads on
# demand. So the description is the number that actually needs a hard budget.
DESCRIPTION_BUDGET = 400
BODY_BUDGET = 4000

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
EM_DASH = "\u2014"


def _skill_path() -> Path:
    return ROOT / "skills/sarathi/SKILL.md"


def _anchors_path() -> Path:
    return ROOT / "skills/sarathi/references/anchors.json"


def check_json_parses() -> list[str]:
    errors = []
    targets = [
        ROOT / ".claude-plugin/plugin.json",
        ROOT / ".claude-plugin/marketplace.json",
        _anchors_path(),
        ROOT / "bench/vendor/provenance.json",
    ]
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
    path = _anchors_path()
    if not path.exists():
        return ["skills/sarathi/references/anchors.json is missing; run bench/build_anchors.py"]
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
    path = _anchors_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        f"{v['ref']}: chapter 13 is recension-ambiguous (34 vs 35 verses)"
        for a in data.get("anchors", [])
        for v in a.get("verses", [])
        if v.get("chapter") == 13
    ]


def check_every_anchor_maps_to_a_failure_mode() -> list[str]:
    """Require every anchor to address a documented failure mode."""
    path = _anchors_path()
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
    for path in [_skill_path()]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if DEVANAGARI.search(text):
            errors.append(f"{path.relative_to(ROOT)}: contains Devanagari that belongs in reference/")
    try:
        arms = build_arms.build_all()
    except (RuntimeError, SystemExit) as exc:
        return errors + [f"cannot build benchmark arms: {exc}"]
    for name, text in arms.items():
        if DEVANAGARI.search(text):
            errors.append(f"generated arm {name}: contains Devanagari that belongs in references/")
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


def check_no_em_dash_in_authored_text() -> list[str]:
    """Keep authored repository text free of em dashes.

    Saved benchmark responses under results/ are evidence produced by models, not
    project prose, so they remain verbatim.

    Vendored competitor arms are exempt for the same reason and a stronger one:
    arms F and G are third-party prompts reproduced byte for byte. Editing them
    to satisfy a house style rule would silently change what the benchmark is
    comparing against, which matters far more than punctuation consistency.
    """
    suffixes = {".md", ".py", ".json", ".yml", ".yaml", ".cff", ".txt"}
    errors = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.parts[0] in {".git", "results"} or "__pycache__" in relative.parts:
            continue
        if relative.parts[:2] == ("bench", "arms"):
            continue
        if relative.parts[:2] == ("bench", "vendor"):
            continue
        if path.name != "Makefile" and path.suffix not in suffixes:
            continue
        if EM_DASH in path.read_text(encoding="utf-8"):
            errors.append(f"{relative}: contains an em dash")
    return errors


def check_arms_differ_only_in_encoding() -> list[str]:
    """Arms B and C must come from the same anchors, or the experiment is invalid.

    If B mentions a principle C omits, a difference in result could be content
    rather than encoding, which would make the comparison unclear.
    """
    anchors_path = _anchors_path()
    if not anchors_path.exists():
        return []

    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    ids = [a["id"] for a in data.get("anchors", [])]
    arms = build_arms.build_all()
    c_text = arms["C"]

    errors = []
    for anchor_id in ids:
        if anchor_id not in c_text:
            errors.append(f"arm C missing anchor {anchor_id}")

    b_text = arms["B"]
    if DEVANAGARI.search(b_text) or re.search(r"\bBG \d", b_text):
        errors.append("arm B contains verse references, so it cannot isolate the full-text condition")
    return errors


def check_ablation_arms() -> list[str]:
    """Arms D and E are the controls that make the result defensible.

    D must carry only wrong references (else it is a second copy of C), and E
    must carry none (else it does not isolate the label).
    """
    anchors_path = _anchors_path()
    if not anchors_path.exists():
        return []

    errors = []
    arms = build_arms.build_all()

    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    correct = {ref for a in data["anchors"] for ref in a["refs"]}

    d_text = arms["D"]
    d_refs = set(re.findall(r"BG \d+\.\d+", d_text))
    overlap = d_refs & correct
    if overlap:
        errors.append(f"arm D contains correct references {sorted(overlap)}, which invalidates the control")
    if not d_refs:
        errors.append("arm D has no references at all")
    if any(r.startswith("BG 13.") for r in d_refs):
        errors.append("arm D uses chapter 13, which is recension-ambiguous")

    e_text = arms["E"]
    if re.search(r"\bBG \d", e_text):
        errors.append("arm E contains references, so it does not isolate the label alone")

    # C and D must cost the same, or the comparison measures length not correctness.
    c_len = len(arms["C"])
    d_len = len(d_text)
    if c_len and abs(c_len - d_len) / c_len > 0.05:
        errors.append(f"arms C ({c_len}) and D ({d_len}) differ by more than 5%, which weakens the comparison")

    return errors


def check_fidelity_probes_cover_anchors() -> list[str]:
    """Every anchor needs a probe, or its reliability is untested."""
    anchors_path = _anchors_path()
    probe_path = ROOT / "bench/fidelity.py"
    if not anchors_path.exists() or not probe_path.exists():
        return []
    data = json.loads(anchors_path.read_text(encoding="utf-8"))
    probes = probe_path.read_text(encoding="utf-8")
    return [
        f"{a['id']}: no fidelity probe, so its pointer reliability is unmeasured"
        for a in data.get("anchors", [])
        if f'"{a["id"]}"' not in probes
    ]


def check_product_and_competitor_arms() -> list[str]:
    """Product arm must be current and competitor arms must match pinned sources."""
    errors = []
    skill_path = _skill_path()
    try:
        arms = build_arms.build_all()
    except (RuntimeError, SystemExit) as exc:
        return [f"cannot build benchmark arms: {exc}"]
    if not skill_path.exists():
        errors.append("product skill is missing")
    else:
        parts = skill_path.read_text(encoding="utf-8").split("---", 2)
        if len(parts) != 3:
            errors.append("SKILL.md has invalid frontmatter")
        elif arms.get("H") != parts[2].lstrip("\n"):
            errors.append("generated arm H does not match deployed Sarathi body")

    provenance_path = ROOT / "bench/vendor/provenance.json"
    if not provenance_path.exists():
        return errors + ["competitor provenance is missing; run bench/vendor_competitors.py"]
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return errors + [f"competitor provenance: {exc}"]

    for name, item in provenance.get("skills", {}).items():
        source_path = ROOT / f"bench/vendor/{name}-SKILL.md"
        arm_name = item.get("arm", "?")
        if not source_path.exists() or arm_name not in arms:
            errors.append(f"{name}: vendored source or generated arm is missing")
            continue
        source = source_path.read_bytes()
        arm = arms[arm_name].encode("utf-8")
        source_hash = hashlib.sha256(source).hexdigest()
        arm_hash = hashlib.sha256(arm).hexdigest()
        if source_hash != item.get("source_sha256"):
            errors.append(f"{name}: source SHA does not match provenance")
        if arm_hash != item.get("arm_sha256"):
            errors.append(f"{name}: arm SHA does not match provenance")
        parts = source.decode("utf-8").split("---", 2)
        if len(parts) != 3 or arm.decode("utf-8") != parts[2].lstrip("\n"):
            errors.append(f"{name}: benchmark arm is not exact post-frontmatter body")
    return errors


def check_plugin_packaging() -> list[str]:
    """Keep Claude, marketplace, citation, and Codex metadata synchronized."""
    errors = []
    plugin_path = ROOT / ".claude-plugin/plugin.json"
    marketplace_path = ROOT / ".claude-plugin/marketplace.json"
    citation_path = ROOT / "CITATION.cff"
    codex_path = ROOT / "skills/sarathi/agents/openai.yaml"
    for path in (plugin_path, marketplace_path, citation_path, codex_path):
        if not path.is_file():
            errors.append(f"{path.relative_to(ROOT)}: missing")
    if errors:
        return errors

    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    entries = marketplace.get("plugins", [])
    if len(entries) != 1:
        errors.append("marketplace must contain exactly one Sarathi plugin entry")
        return errors
    entry = entries[0]
    versions = {
        plugin.get("version"),
        marketplace.get("metadata", {}).get("version"),
        entry.get("version"),
    }
    if len(versions) != 1 or None in versions:
        errors.append(f"plugin versions disagree: {sorted(str(v) for v in versions)}")
    if plugin.get("name") != "sarathi" or entry.get("name") != "sarathi":
        errors.append("Claude plugin and marketplace names must both be sarathi")

    citation = citation_path.read_text(encoding="utf-8")
    version = plugin.get("version")
    if version and f"version: {version}" not in citation:
        errors.append("CITATION.cff version does not match plugin.json")
    codex = codex_path.read_text(encoding="utf-8")
    for required in ('display_name: "Sarathi"', "$sarathi"):
        if required not in codex:
            errors.append(f"skills/sarathi/agents/openai.yaml missing {required}")
    return errors


CHECKS = [
    ("json parses", check_json_parses),
    ("every verse has a source", check_every_verse_has_a_source),
    ("no chapter-13 anchors", check_no_chapter_13),
    ("anchors map to failure modes", check_every_anchor_maps_to_a_failure_mode),
    ("no devanagari in frequently loaded prompts", check_no_devanagari_in_hot_path),
    ("skill within budget", check_skill_budget),
    ("authored text has no em dashes", check_no_em_dash_in_authored_text),
    ("arms differ only in encoding", check_arms_differ_only_in_encoding),
    ("control arms are valid", check_ablation_arms),
    ("fidelity probes cover anchors", check_fidelity_probes_cover_anchors),
    ("product and competitor arms are pinned", check_product_and_competitor_arms),
    ("plugin packaging is synchronized", check_plugin_packaging),
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
