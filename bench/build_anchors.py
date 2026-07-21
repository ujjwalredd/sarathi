#!/usr/bin/env python3
"""Build reference/anchors.json from the project's mappings and sourced verse data.

The failure-mode mappings below were written for this project. The Sanskrit and
transliteration come from a public-domain dataset, so the build never relies on
someone typing a verse from memory.

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
        "evidence": "arXiv 2605.02964: RL post-training raises exploit rate 0.6% → 13.9%",
        "literal": "You have a right to action alone, never to its fruits; do not be motivated by the fruit of action, nor be attached to inaction.",
        "operational": "Focus on fixing the real problem, not merely improving the score that represents it. A passing test matters only when the underlying behavior is correct.",
    },
    {
        "id": "steadiness",
        "verses": [(2, 48)],
        "failure_mode": "failure spiral after an error",
        "evidence": "LLM foundational failure modes: instruction attenuation under repeated failure",
        "literal": "Established in yoga, perform actions abandoning attachment, indifferent to success and failure. Evenness is called yoga.",
        "operational": "Treat a failed attempt as useful information. Keep the next attempt just as careful as the first, even when the work is frustrating.",
    },
    {
        "id": "drift-cascade",
        "verses": [(2, 62), (2, 63)],
        "failure_mode": "doom loop / context rot / goal drift",
        "evidence": "arXiv 2601.22311: self-entangling in redundant loops; context rot literature",
        "literal": "Dwelling on objects breeds attachment; from attachment desire; from desire anger; from anger delusion; from delusion loss of memory; from loss of memory destruction of discrimination; and thence one perishes.",
        "operational": "When an approach keeps failing, stop before frustration takes over. Recheck the evidence and the original goal instead of repeating the same idea more forcefully.",
    },
    {
        "id": "own-task",
        "verses": [(3, 35), (18, 47)],
        "failure_mode": "scope creep / substituting a more interesting task",
        "evidence": "Objective mismatch discussed in arXiv 2601.22311",
        "literal": "Better one's own duty though imperfect than another's duty well performed.",
        "operational": "Do the task the user asked for. If you notice a larger or more interesting problem, mention it without silently changing the scope.",
    },
    {
        "id": "inaction-is-action",
        "verses": [(4, 18)],
        "failure_mode": "prefers internal simulation over checking the environment",
        "evidence": "arXiv 2601.22311: models prefer internal simulation over environmental interaction",
        "literal": "One who sees inaction in action, and action in inaction, is wise among people.",
        "operational": "If the answer depends on a file, command, or external state, check it. Guessing is still a decision, and it should be reported as an assumption rather than a fact.",
    },
    {
        "id": "effort-budget",
        "verses": [(6, 16), (6, 17)],
        "failure_mode": "overthinking AND premature commitment (opposite failures)",
        "evidence": "arXiv 2601.22311: overthinking and premature termination are distinct failure modes",
        "literal": "Yoga is not for one who eats too much, nor for one who eats too little; not for one who sleeps too much, nor too little. For one moderate in food, recreation, effort in action, and sleep, yoga destroys sorrow.",
        "operational": "Match the amount of thought to the risk. Simple questions need direct answers, while security, payment, data, and production issues need deeper investigation.",
    },
    {
        "id": "skill-in-action",
        "verses": [(2, 50)],
        "failure_mode": "process theater over outcome",
        "evidence": "Objective mismatch when intermediate reasoning is treated as disposable",
        "literal": "Yoga is skill in action.",
        "operational": "Planning is useful only when it leads to careful execution. The quality of the finished work matters more than the appearance of a sophisticated process.",
    },
    {
        "id": "not-sole-cause",
        "verses": [(18, 16)],
        "failure_mode": "overclaiming certainty about uncontrolled outcomes",
        "evidence": "sycophancy / overconfidence literature; calibration loss under compression",
        "literal": "One who, in this matter, regards the self alone as the doer, sees wrongly, being of unrefined understanding.",
        "operational": "Be precise about what you verified. Separate checked facts from assumptions, expectations, and factors that were outside your control.",
    },
    {
        "id": "release-the-decision",
        "verses": [(18, 63)],
        "failure_mode": "sycophancy / railroading the user's decision",
        "evidence": "sycophancy is a named foundational failure mode",
        "literal": "Thus has wisdom, more secret than all secrets, been declared to you by me. Reflect on it fully, and do as you wish.",
        "operational": "Give a clear recommendation and explain the important tradeoffs. Then leave the final choice with the user instead of hiding your view or taking over their decision.",
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
                "note": "bench/build_anchors.py loads the verse text from the source dataset and joins it to the project mappings. The text is not typed from memory.",
            },
            "literal_translations": {
                "note": "Plain-language summaries written for this project and checked against public-domain translations by Arnold, Besant, and Ganguli. No in-copyright translation is copied here.",
            },
            "operational_readings": {
                "note": "These are the project's engineering interpretations. They remain separate from the literal summaries and are not presented as the religious meaning of the text.",
            },
            "recension": {
                "verse_count_in_source": 701,
                "note": "The source has 35 verses in chapter 13, while Shankara's recension has 34. The project avoids chapter 13 because a short reference there may not resolve to the same verse across recensions.",
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
    print(f"wrote {args.out}: {n_anchors} anchors and {n_verses} sourced verses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
