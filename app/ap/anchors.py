"""Few-shot anchoring from official, human-scored AP samples.

Calibrating an LLM scorer to the official score scale is far more reliable when
the prompt shows it REAL essays with their REAL College Board scores. We draw
anchors only from set-1 so that set-2 can serve as a leakage-free validation
hold-out (see app/ap/eval.py).

Each anchor shows a trimmed essay excerpt + the official Row A/B/C scores, so the
model sees concretely what (e.g.) "Row B = 2" vs "Row B = 4" looks like.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = _ROOT / "data" / "ap" / "samples.json"

ANCHOR_YEAR = "2024"     # year+set reserved for anchoring (NEVER used for validation)
ANCHOR_SETS = {"1"}
EXCERPT_CHARS = 700


@lru_cache(maxsize=1)
def _all() -> list[dict]:
    if not SAMPLES.exists():
        return []
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def is_anchor(record: dict) -> bool:
    return (record.get("year") == ANCHOR_YEAR
            and record.get("set") in ANCHOR_SETS)


def anchors_for(frq_type: str, max_anchors: int = 3) -> list[dict]:
    rows = [
        r for r in _all()
        if r["frq_type"] == frq_type
        and r.get("verified")
        and is_anchor(r)
    ]
    # diversity: prefer a spread of total scores (low / mid / high)
    rows.sort(key=lambda r: r["scores"]["total"])
    if len(rows) <= max_anchors:
        return rows
    # pick evenly across the sorted-by-score list
    step = (len(rows) - 1) / (max_anchors - 1) if max_anchors > 1 else 0
    return [rows[round(i * step)] for i in range(max_anchors)]


def anchor_block(frq_type: str, max_anchors: int = 3) -> str:
    rows = anchors_for(frq_type, max_anchors)
    if not rows:
        return ""
    out = [
        "CALIBRATION ANCHORS — real student responses with OFFICIAL College "
        "Board scores. Use these to calibrate your scale; do not quote them.",
    ]
    for r in rows:
        s = r["scores"]
        excerpt = " ".join(r["essay_text"].split())[:EXCERPT_CHARS]
        out.append(
            f"\n[Official score: Row A {s['A']}/1, Row B {s['B']}/4, "
            f"Row C {s['C']}/1 → total {s['total']}/6]\nEXCERPT: {excerpt}…"
        )
    return "\n".join(out)


def sophistication_block(frq_type: str, n_each: int = 2) -> str:
    """Contrastive anchors for the dedicated Row C judge: real essays that DID
    and DID NOT earn the sophistication point, with their official verdict."""
    pool = [r for r in _all() if r.get("verified") and is_anchor(r)]
    same = [r for r in pool if r["frq_type"] == frq_type]
    # synthesis set-1 has no C=1 anchor → fall back to the full anchor pool
    src = same if any(r["scores"]["C"] == 1 for r in same) else pool
    pos = [r for r in src if r["scores"]["C"] == 1][:n_each]
    neg = [r for r in src if r["scores"]["C"] == 0][:n_each]
    if not pos and not neg:
        return ""
    out = ["CONTRASTIVE ANCHORS (official College Board verdicts on the "
           "sophistication point):"]
    for r in pos:
        out.append(f"\n[EARNED sophistication — Row C = 1] EXCERPT: "
                   f"{' '.join(r['essay_text'].split())[:EXCERPT_CHARS]}…")
    for r in neg:
        out.append(f"\n[did NOT earn it — Row C = 0] EXCERPT: "
                   f"{' '.join(r['essay_text'].split())[:EXCERPT_CHARS]}…")
    return "\n".join(out)


def available() -> bool:
    return bool(_all())
