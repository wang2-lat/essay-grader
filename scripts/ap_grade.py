"""CLI: score an essay with the AP analytic rubric.

Usage:
    ./.venv/bin/python scripts/ap_grade.py <frq_type> <essay_file> [--passes N]

frq_type: synthesis | rhetorical_analysis | argument
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
# grader reads its config at import time → load .env FIRST (see project memory).
load_dotenv(_ROOT / ".env")

from app.ap import scorer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frq_type", choices=["synthesis", "rhetorical_analysis", "argument"])
    ap.add_argument("essay_file")
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--annotate", action="store_true",
                    help="also produce span-anchored margin notes")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    args = ap.parse_args()

    essay = Path(args.essay_file).read_text(encoding="utf-8")
    result = scorer.score_essay(
        essay, args.frq_type, passes=args.passes, annotate=args.annotate,
    )

    if not result.get("ok"):
        print("ERROR:", result.get("error"), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    r = result["rows"]
    print(f"\n=== {result['frq_label']}  —  TOTAL {result['total']}/6  "
          f"(model: {result['meta']['model']}, passes: {result['meta']['passes']}) ===\n")
    a, b, c = r["A_thesis"], r["B_evidence_commentary"], r["C_sophistication"]
    print(f"Row A · Thesis ............. {a['score']}/1")
    print(f"   thesis: {a['quote'][:120]}")
    print(f"   {a['rationale']}\n")
    print(f"Row B · Evidence & Commentary {b['score']}/4"
          f"{'  [grammar gate applied]' if b['grammar_gate_applied'] else ''}")
    print(f"   line of reasoning: {b['line_of_reasoning']}")
    print(f"   evidence:   {b['evidence']}")
    print(f"   commentary: {b['commentary']}")
    print(f"   {b['rationale']}\n")
    print(f"Row C · Sophistication ..... {c['score']}/1")
    print(f"   {c['rationale']}\n")
    print(f"Teacher comment: {result['overall_comment']}\n")
    print("Top fixes:")
    for i, fx in enumerate(result["top_fixes"], 1):
        print(f"  {i}. {fx}")

    anns = result.get("annotations") or []
    if anns:
        located = sum(1 for a in anns if a.get("located"))
        print(f"\nMargin notes ({located}/{len(anns)} anchored to the text):")
        for a in anns:
            tag = a.get("type", "note")
            flag = "" if a.get("located") else "  [unanchored]"
            print(f"  • [{tag}] “{a.get('quote','')[:60]}”{flag}")
            print(f"      {a.get('comment','')}")
            if a.get("suggestion"):
                print(f"      💡 {a['suggestion']}")
    if result["meta"]["passes"] > 1:
        print(f"\n(self-consistency samples: {result['meta']['row_score_samples']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
