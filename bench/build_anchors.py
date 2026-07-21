#!/usr/bin/env python3
"""Generate reference/anchors.json by joining failure-mode mappings to source text.

The mappings below are this project's own editorial work. The Sanskrit is not:
it is fetched from a public-domain dataset and joined programmatically, so no
verse text is ever typed from memory.

That rule exists because citation hallucination runs 13-21% even in retrieval-
grounded systems, and a project whose entire mechanism is "the reference
resolves correctly" cannot afford a wrong reference.

Usage:
    python bench/build_anchors.py --source /tmp/gita_verse.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_NAME = "gita/gita"
SOURCE_URL = "https://github.com/gita/gita"
SOURCE_LICENSE = "Unlicense (public domain dedication)"
SOURCE_RAW = "https://raw.githubusercontent.com/gita/gita/main/data/verse.json"

# Editorial layer. `operational` is this project's engineering reading and is
# deliberately kept in a separate field from `literal` - the text is being used
# as a mnemonic for agent reasoning, which is not a claim about what it means
# devotionally.
ANCHORS = [
    {
        "id": "action-not-fruit",
        "verses": [(2, 47)],
        "failure_mode": "reward hacking / specification gaming",
        "evidence": "arXiv 2605.02964 — RL post-training raises exploit rate 0.6% → 13.9%",
        "literal": "You have a right to action alone, never to its fruits; do not be motivated by the fruit of action, nor be attached to inaction.",
        "operational": "Optimize the action, not the metric. Passing the test is the fruit; correct code is the action. If you find yourself shaping output to satisfy a check rather than the goal the check stands for, stop.",
    },
    {
        "id": "steadiness",
        "verses": [(2, 48)],
        "failure_mode": "failure spiral after an error",
        "evidence": "LLM foundational failure modes — instruction attenuation under repeated failure",
        "literal": "Established in yoga, perform actions abandoning attachment, indifferent to success and failure. Evenness is called yoga.",
        "operational": "A failed attempt is information, not a verdict. Do not let it destabilize the next attempt. Same care after the fourth failure as the first.",
    },
    {
        "id": "drift-cascade",
        "verses": [(2, 62), (2, 63)],
        "failure_mode": "doom loop / context rot / goal drift",
        "evidence": "arXiv 2601.22311 — self-entangling in redundant loops; context rot literature",
        "literal": "Dwelling on objects breeds attachment; from attachment desire; from desire anger; from anger delusion; from delusion loss of memory; from loss of memory destruction of discrimination; and thence one perishes.",
        "operational": "The eight-stage collapse. Fixation on a blocked approach breeds frustration, frustration distorts judgment, distorted judgment corrupts memory of the original objective, and corrupted memory destroys reasoning. Catch it at stage one: notice fixation before it becomes drift.",
    },
    {
        "id": "own-task",
        "verses": [(3, 35), (18, 47)],
        "failure_mode": "scope creep / substituting a more interesting task",
        "evidence": "objective mismatch — arXiv 2601.22311",
        "literal": "Better one's own duty though imperfect than another's duty well performed.",
        "operational": "Do the task you were given, imperfectly, rather than an adjacent task beautifully. Finding a more interesting problem nearby is not permission to solve that one instead. Surface it; do not silently switch.",
    },
    {
        "id": "inaction-is-action",
        "verses": [(4, 18)],
        "failure_mode": "prefers internal simulation over checking the environment",
        "evidence": "arXiv 2601.22311 — models prefer internal simulation over environmental interaction",
        "literal": "One who sees inaction in action, and action in inaction, is wise among people.",
        "operational": "Not checking is a choice with consequences. Reasoning about what a file probably contains is an action - the action of deciding not to read it. Name that decision instead of sliding into it.",
    },
    {
        "id": "effort-budget",
        "verses": [(6, 16), (6, 17)],
        "failure_mode": "overthinking AND premature commitment (opposite failures)",
        "evidence": "arXiv 2601.22311 — overthinking and premature termination are distinct failure modes",
        "literal": "Yoga is not for one who eats too much, nor for one who eats too little; not for one who sleeps too much, nor too little. For one moderate in food, recreation, effort in action, and sleep, yoga destroys sorrow.",
        "operational": "Two-sided budget rule. Most guidance only warns against one direction. Too little thought ships the wrong thing; too much burns the budget and still ships. Ask which failure you are closer to right now.",
    },
    {
        "id": "skill-in-action",
        "verses": [(2, 50)],
        "failure_mode": "process theater over outcome",
        "evidence": "objective mismatch — intermediate reasoning treated as disposable",
        "literal": "Yoga is skill in action.",
        "operational": "The quality of the doing is the deliverable. Elaborate planning that produces a careless edit has the sequence backwards.",
    },
    {
        "id": "not-sole-cause",
        "verses": [(18, 16)],
        "failure_mode": "overclaiming certainty about uncontrolled outcomes",
        "evidence": "sycophancy / overconfidence literature; calibration loss under compression",
        "literal": "One who, in this matter, regards the self alone as the doer, sees wrongly, being of unrefined understanding.",
        "operational": "You did not control the environment, the network, the other process, or what the user did not tell you. Report what you verified as verified and what you assumed as assumed.",
    },
    {
        "id": "release-the-decision",
        "verses": [(18, 63)],
        "failure_mode": "sycophancy / railroading the user's decision",
        "evidence": "sycophancy is a named foundational failure mode",
        "literal": "Thus has wisdom, more secret than all secrets, been declared to you by me. Reflect on it fully, and do as you wish.",
        "operational": "Counsel completely, then release the decision. Krishna's last word after 700 verses is not 'therefore obey' - it is 'having considered, choose'. Give the real recommendation, then let the user own the call. Neither withhold your view nor overrule theirs.",
    },
]


def load_source(path: Path) -> dict[tuple[int, int], dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read source {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    return {(r["chapter_number"], r["verse_number"]): r for r in data}


def normalize(text: str) -> str:
    return " ".join(text.split())


def build(index: dict[tuple[int, int], dict]) -> dict:
    anchors = []
    missing = []

    for spec in ANCHORS:
        verses = []
        for chapter, number in spec["verses"]:
            record = index.get((chapter, number))
            if record is None:
                missing.append(f"BG {chapter}.{number}")
                continue
            # Chapter 13 numbering differs by recension (34 vs 35 verses), so a
            # BG 13.x pointer is genuinely ambiguous. No anchor uses chapter 13.
            if chapter == 13:
                missing.append(f"BG {chapter}.{number} (chapter 13 is recension-ambiguous)")
                continue
            verses.append({
                "ref": f"BG {chapter}.{number}",
                "chapter": chapter,
                "verse": number,
                "devanagari": normalize(record["text"]),
                "iast": normalize(record["transliteration"]),
                "source": SOURCE_RAW,
            })

        anchors.append({
            "id": spec["id"],
            "refs": [v["ref"] for v in verses],
            "failure_mode": spec["failure_mode"],
            "evidence": spec["evidence"],
            "literal": spec["literal"],
            "operational": spec["operational"],
            "verses": verses,
        })

    if missing:
        print("error: unresolved verses: " + ", ".join(missing), file=sys.stderr)
        raise SystemExit(1)

    return {
        "_provenance": {
            "sanskrit_and_transliteration": {
                "source": SOURCE_NAME,
                "url": SOURCE_URL,
                "raw": SOURCE_RAW,
                "license": SOURCE_LICENSE,
                "note": "Verse text is fetched and joined programmatically by bench/build_anchors.py. It is never typed by hand.",
            },
            "literal_translations": {
                "note": "Plain-sense renderings by this project, checked against public-domain translations (Arnold 1885, Besant 1895, Ganguli 1883-96). Not from any in-copyright translation.",
            },
            "operational_readings": {
                "note": "This project's engineering interpretation. Deliberately kept in a field separate from `literal`. These are mnemonics for agent reasoning and are not claims about the text's religious meaning.",
            },
            "recension": {
                "verse_count_in_source": 701,
                "note": "The source follows a recension with 35 verses in chapter 13; Shankara's has 34. 'The Gita has 700 verses' is a recension choice, not a fact. No anchor uses chapter 13, because a BG 13.x pointer does not resolve unambiguously - which is precisely the failure this project measures.",
            },
        },
        "anchors": anchors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reference/anchors.json from a source dataset.")
    parser.add_argument("--source", type=Path, default=Path("/tmp/gita_verse.json"))
    parser.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "reference/anchors.json")
    args = parser.parse_args()

    index = load_source(args.source)
    data = build(index)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    n_anchors = len(data["anchors"])
    n_verses = sum(len(a["verses"]) for a in data["anchors"])
    print(f"wrote {args.out} — {n_anchors} anchors, {n_verses} verses, all sourced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
