"""Honest quality check for AP margin annotations.

IMPORTANT — what this does and does NOT measure.

There is NO official gold standard for inline teacher feedback, so — unlike the
score evaluation in app/ap/eval.py (which reports QWK against real College Board
scores) — this script CANNOT and does NOT claim the annotations are "correct".
Inventing an accuracy number here would be a fake benchmark.

What it DOES measure are the objective, checkable properties the feature is built
to guarantee:

  - anchored_rate   : fraction of notes whose quote resolves verbatim to a real
                      span (the deterministic-gate pass rate — the one thing we
                      truly verify in code).
  - count_in_band   : fraction of essays landing in the target 6-12 notes.
  - coverage        : do anchored notes spread across the start/middle/end thirds
                      of the essay, or clump in one place?
  - row_spread      : do the notes touch more than one rubric row (A/B/C), i.e.
                      is the feedback diagnostic across the rubric, not one-note?
  - has_praise      : does each essay get at least one strength called out?

Read these as "is the feature behaving as designed", not "is the advice good".
Judging advice QUALITY still needs a human reading the notes.

Usage:
    ./.venv/bin/python scripts/ap_annotate_check.py [--n 4] [--frq argument]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")  # grader reads config at import → load .env first

from app.ap import eval as ap_eval  # noqa: E402
from app.ap import scorer  # noqa: E402


def _thirds(anns: list[dict], essay_len: int) -> set[str]:
    """Which thirds of the essay the anchored notes fall into."""
    hit = set()
    for a in anns:
        if not a.get("located") or essay_len <= 0:
            continue
        frac = a["start"] / essay_len
        hit.add("start" if frac < 1 / 3 else "middle" if frac < 2 / 3 else "end")
    return hit


def check_one(sample: dict) -> dict:
    essay = sample["essay_text"]
    res = scorer.score_essay(essay, sample["frq_type"], passes=1, annotate=True)
    if not res.get("ok"):
        return {"id": sample["sample_id"], "error": res.get("error")}
    anns = res.get("annotations") or []
    anchored = [a for a in anns if a.get("located")]
    rows = {a.get("row") for a in anchored} - {"-"}
    return {
        "id": f"{sample.get('year','?')}/{sample['frq_type'][:3]}/{sample['sample_id']}",
        "n_notes": len(anns),
        "anchored": len(anchored),
        "anchored_rate": len(anchored) / len(anns) if anns else 0.0,
        "in_band": 6 <= len(anns) <= 12,
        "thirds": _thirds(anns, len(essay)),
        "rows_touched": rows,
        "has_praise": any(a.get("type") == "praise" for a in anns),
        # why zero notes, if zero — scorer records annotate failures here
        "soft_errors": [e for e in res.get("meta", {}).get("errors", [])
                        if str(e).startswith("annotate")],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4, help="how many held-out essays to check")
    ap.add_argument("--frq", default=None)
    args = ap.parse_args()

    samples = ap_eval.load_samples(frq_type=args.frq, holdout=True)[: args.n]
    if not samples:
        print("No samples found. Build them with scripts/build_ap_samples.py first.",
              file=sys.stderr)
        return 1

    rows = [check_one(s) for s in samples]
    ok = [r for r in rows if "error" not in r]

    print(f"\n=== AP annotation FAITHFULNESS/COVERAGE check — model "
          f"{scorer.grader.current_model()}, n={len(ok)} ===")
    print("(NOT an accuracy score — there is no inline-feedback gold standard; "
          "this checks the feature behaves as designed.)\n")
    for r in rows:
        if "error" in r:
            print(f"  {r['id']}: ERROR {r['error']}")
            continue
        cov = "".join(s[0].upper() if s in r["thirds"] else "·"
                      for s in ("start", "middle", "end"))
        print(f"  {r['id']:>16}: {r['anchored']}/{r['n_notes']} anchored "
              f"({r['anchored_rate']:.0%}) | band {'✓' if r['in_band'] else '✗'} "
              f"| coverage {cov} | rows {''.join(sorted(r['rows_touched'])) or '—'} "
              f"| praise {'✓' if r['has_praise'] else '✗'}")
        for e in r.get("soft_errors", []):
            print(f"        ↳ {e}")

    if ok:
        n = len(ok)
        print("\nAggregate:")
        print(f"  mean anchored_rate : {sum(r['anchored_rate'] for r in ok)/n:.0%}  "
              f"(verbatim-quote resolution — the only hard-verified metric)")
        print(f"  in 6-12 band       : {sum(r['in_band'] for r in ok)}/{n}")
        print(f"  all 3 thirds       : {sum(len(r['thirds'])==3 for r in ok)}/{n}")
        print(f"  >1 rubric row      : {sum(len(r['rows_touched'])>1 for r in ok)}/{n}")
        print(f"  has a praise note  : {sum(r['has_praise'] for r in ok)}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
