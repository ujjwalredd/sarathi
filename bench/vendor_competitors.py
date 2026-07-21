#!/usr/bin/env python3
"""Vendor pinned competitor skills and record derived arm provenance.

The full upstream SKILL.md files are retained for audit. Benchmark arms contain
the exact post-frontmatter bodies an explicitly loaded skill contributes. No
competitor prose is edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

import build_arms

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "bench/vendor"

SPECS = {
    "caveman": {
        "arm": "F",
        "repo": "https://github.com/JuliusBrussee/caveman",
        "revision": "0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0",
        "path": "skills/caveman/SKILL.md",
        "license": "MIT",
        "license_url": "https://github.com/JuliusBrussee/caveman/blob/0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0/LICENSE",
        "copyright": "Copyright (c) 2026 Julius Brussee",
    },
    "ponytail": {
        "arm": "G",
        "repo": "https://github.com/DietrichGebert/ponytail",
        "revision": "16f29800fd2681bdf24f3eb4ccffe38be3baec6b",
        "path": "skills/ponytail/SKILL.md",
        "license": "MIT",
        "license_url": "https://github.com/DietrichGebert/ponytail/blob/16f29800fd2681bdf24f3eb4ccffe38be3baec6b/LICENSE",
        "copyright": "Copyright (c) 2026 DietrichGebert",
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_url(spec: dict) -> str:
    owner_repo = spec["repo"].removeprefix("https://github.com/")
    return f"https://raw.githubusercontent.com/{owner_repo}/{spec['revision']}/{spec['path']}"


def load_source(spec: dict, override: Path | None) -> bytes:
    if override is not None:
        return override.read_bytes()
    try:
        with urllib.request.urlopen(raw_url(spec), timeout=30) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"failed to fetch {raw_url(spec)}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Vendor pinned competitor skills")
    parser.add_argument("--caveman-source", type=Path)
    parser.add_argument("--ponytail-source", type=Path)
    args = parser.parse_args()

    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    overrides = {
        "caveman": args.caveman_source,
        "ponytail": args.ponytail_source,
    }
    provenance = {"schema_version": 1, "generated_by": "bench/vendor_competitors.py", "skills": {}}

    for name, spec in SPECS.items():
        source = load_source(spec, overrides[name])
        text = source.decode("utf-8")
        body = build_arms.skill_body(text).encode("utf-8")
        if f"name: {name}" not in text.split("---", 2)[1]:
            raise RuntimeError(f"source for {name} has unexpected frontmatter")

        vendor_path = VENDOR_DIR / f"{name}-SKILL.md"
        vendor_path.write_bytes(source)
        provenance["skills"][name] = {
            **spec,
            "source_url": raw_url(spec),
            "source_sha256": digest(source),
            "source_bytes": len(source),
            "arm_sha256": digest(body),
            "arm_bytes": len(body),
            "transformation": "removed YAML frontmatter; body bytes unchanged",
        }

    (VENDOR_DIR / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name, item in provenance["skills"].items():
        print(f"{name}: {item['revision'][:8]}  arm {item['arm']}  {item['arm_bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
