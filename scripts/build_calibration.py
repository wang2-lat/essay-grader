"""Extract calibration anchors from the ELLIPSE corpus.

Picks a handful of real, human-scored essays spread across the score range so
the grading engine can anchor its scale to professionally rated examples.
Output: app/data/calibration.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ellipse_train.csv"
OUT = ROOT / "app" / "data" / "calibration.json"

DIMS = ["Overall", "Cohesion", "Syntax", "Vocabulary",
        "Phraseology", "Grammar", "Conventions"]

# Anchor on these Overall bands; one representative essay each.
TARGET_BANDS = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
# Keep anchor essays readable in the prompt — trim very long ones.
MAX_CHARS = 1400


def pick(df: pd.DataFrame, band: float) -> dict | None:
    pool = df[df["Overall"] == band]
    if pool.empty:
        return None
    # Prefer a mid-length essay (most representative).
    pool = pool.assign(_len=pool["full_text"].str.len())
    pool = pool.sort_values("_len")
    row = pool.iloc[len(pool) // 2]
    text = str(row["full_text"]).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0] + " […]"
    return {
        "grade": int(row["grade"]) if pd.notna(row["grade"]) else None,
        "scores": {d.lower(): float(row[d]) for d in DIMS},
        "text": text,
    }


def main() -> None:
    df = pd.read_csv(RAW)
    anchors = []
    for band in TARGET_BANDS:
        a = pick(df, band)
        if a:
            anchors.append(a)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(anchors, ensure_ascii=False, indent=2))
    print(f"Wrote {len(anchors)} calibration anchors -> {OUT}")
    # quick distribution report
    print("\nOverall score distribution in corpus:")
    print(df["Overall"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
