"""Honest accuracy evaluation for the AP scorer.

Runs the scorer over the held-out, officially-scored sample essays and reports
agreement with the official human scores using:
  - Quadratic Weighted Kappa (QWK)  — the standard automated-essay-scoring metric
  - exact agreement rate
  - adjacent agreement rate (within 1 point)
for the TOTAL (0-6) and for each Row (A 0-1, B 0-4, C 0-1).

QWK ceiling reality check (2025 literature): even SOTA systems reach only
~0.6 QWK on open essay datasets. Treat anything in that range as "approaching a
second human reader", NOT as an oracle.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from . import anchors as _anchors
from . import scorer

_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = _ROOT / "data" / "ap" / "samples.json"


def quadratic_weighted_kappa(y_true: list[int], y_pred: list[int],
                             min_r: int, max_r: int) -> float:
    """QWK over the integer rating range [min_r, max_r]."""
    n = max_r - min_r + 1
    if n <= 1 or not y_true:
        return float("nan")
    O = [[0] * n for _ in range(n)]
    for a, b in zip(y_true, y_pred):
        O[a - min_r][b - min_r] += 1
    hist_t = [0] * n
    hist_p = [0] * n
    for a, b in zip(y_true, y_pred):
        hist_t[a - min_r] += 1
        hist_p[b - min_r] += 1
    total = len(y_true)
    num = den = 0.0
    for i in range(n):
        for j in range(n):
            w = ((i - j) ** 2) / ((n - 1) ** 2)
            e = hist_t[i] * hist_p[j] / total
            num += w * O[i][j]
            den += w * e
    return 1.0 - num / den if den else float("nan")


def _agreement(y_true: list[int], y_pred: list[int]) -> tuple[float, float]:
    if not y_true:
        return float("nan"), float("nan")
    exact = sum(1 for a, b in zip(y_true, y_pred) if a == b) / len(y_true)
    adj = sum(1 for a, b in zip(y_true, y_pred) if abs(a - b) <= 1) / len(y_true)
    return exact, adj


def load_samples(verified_only: bool = True,
                 frq_type: str | None = None,
                 sets: Iterable[str] | None = None,
                 holdout: bool = False) -> list[dict[str, Any]]:
    """Load samples. holdout=True returns every verified sample that is NOT an
    anchor (the leakage-free validation pool across all years)."""
    data = json.loads(SAMPLES.read_text(encoding="utf-8"))
    out = []
    for r in data:
        if verified_only and not r.get("verified"):
            continue
        if holdout and _anchors.is_anchor(r):
            continue
        if frq_type and r["frq_type"] != frq_type:
            continue
        if sets and r["set"] not in set(sets):
            continue
        out.append(r)
    return out


def evaluate(samples: list[dict[str, Any]], *, passes: int = 3) -> dict[str, Any]:
    rows = {"A": (0, 1), "B": (0, 4), "C": (0, 1), "total": (0, 6)}
    truth = {k: [] for k in rows}
    pred = {k: [] for k in rows}
    per_essay = []

    for s in samples:
        res = scorer.score_essay(s["essay_text"], s["frq_type"], passes=passes)
        if not res.get("ok"):
            per_essay.append({"id": s["sample_id"], "frq": s["frq_type"],
                              "error": res.get("error")})
            continue
        pa = res["rows"]["A_thesis"]["score"]
        pb = res["rows"]["B_evidence_commentary"]["score"]
        pc = res["rows"]["C_sophistication"]["score"]
        ta, tb, tc = s["scores"]["A"], s["scores"]["B"], s["scores"]["C"]
        for k, (tv, pv) in {"A": (ta, pa), "B": (tb, pb), "C": (tc, pc),
                            "total": (ta + tb + tc, pa + pb + pc)}.items():
            truth[k].append(tv)
            pred[k].append(pv)
        per_essay.append({
            "id": f"{s.get('year','?')}/{s['frq_type'][:3]}/{s['set']}/{s['sample_id']}",
            "official": f"{ta}-{tb}-{tc}={ta+tb+tc}",
            "predicted": f"{pa}-{pb}-{pc}={pa+pb+pc}",
            "abs_err_total": abs((ta + tb + tc) - (pa + pb + pc)),
        })

    metrics = {}
    for k, (lo, hi) in rows.items():
        ex, adj = _agreement(truth[k], pred[k])
        metrics[k] = {
            "n": len(truth[k]),
            "qwk": round(quadratic_weighted_kappa(truth[k], pred[k], lo, hi), 3),
            "exact_agreement": round(ex, 3),
            "adjacent_agreement": round(adj, 3),
        }
    return {"metrics": metrics, "per_essay": per_essay, "passes": passes,
            "model": scorer.grader.current_model(), "n_samples": len(samples)}


def _print_report(report: dict[str, Any]) -> None:
    print(f"\n=== AP scorer validation — model {report['model']}, "
          f"passes {report['passes']}, n={report['n_samples']} ===\n")
    print(f"{'category':>8} | {'n':>3} | {'QWK':>6} | {'exact':>6} | {'adj±1':>6}")
    print("-" * 42)
    for k in ("A", "B", "C", "total"):
        m = report["metrics"][k]
        print(f"{k:>8} | {m['n']:>3} | {m['qwk']:>6} | "
              f"{m['exact_agreement']:>6} | {m['adjacent_agreement']:>6}")
    print("\nper-essay (official vs predicted, Row A-B-C = total):")
    for e in report["per_essay"]:
        if "error" in e:
            print(f"  {e['id']}: ERROR {e['error']}")
        else:
            flag = "" if e["abs_err_total"] == 0 else (" *" if e["abs_err_total"] == 1 else " **")
            print(f"  {e['id']:>28}: official {e['official']:>9} | "
                  f"predicted {e['predicted']:>9} | Δtotal {e['abs_err_total']}{flag}")


if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")  # grader reads config at import; ensure it's set

    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--frq", default=None)
    ap.add_argument("--sets", default=None, help="comma list, e.g. 2 (hold-out set)")
    ap.add_argument("--holdout", action="store_true",
                    help="evaluate on ALL non-anchor verified samples (all years)")
    args = ap.parse_args()
    sets = args.sets.split(",") if args.sets else None
    samples = load_samples(frq_type=args.frq, sets=sets, holdout=args.holdout)
    _print_report(evaluate(samples, passes=args.passes))
