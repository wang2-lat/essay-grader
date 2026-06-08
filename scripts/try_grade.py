"""Quick standalone check of the grading engine (needs ANTHROPIC_API_KEY).

Usage:
    ./.venv/bin/python scripts/try_grade.py
"""
from __future__ import annotations

import json
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, ".")
from app.core import grader  # noqa: E402

SAMPLE = (
    "Many people think that phones should be banned in school. I disagree with this "
    "opinion because phones can help students a lot. First, phones is a good tool for "
    "searching information when the teacher ask a question. Second, if there is a "
    "emergency, students can call their parents quickly. Some people say phones make "
    "students distracted, but I think it depends on the student themself. In conclusion, "
    "phones should not be banned because they are usefull and important in our daily life."
)


def main() -> None:
    print("Grading sample essay with model:", grader.MODEL)
    result = grader.grade_essay(
        essay_text=SAMPLE,
        assignment_prompt="Should phones be banned in school? Argue your position.",
        grade_level="Grade 9",
        essay_type="argumentative essay",
    )
    if result.get("rubric_check"):
        print("\n=== RUBRIC CHECK (reason-before-score) ===")
        for k, v in result["rubric_check"].items():
            print(f"  {k:12s} {v}")
    print("\n=== SCORES ===")
    for k, v in result["scores"].items():
        print(f"  {k:12s} {v}")
    print("\n=== SUMMARY ===\n ", result["summary"])
    print("\n=== STRENGTHS ===")
    for s in result["strengths"]:
        print("  +", s)
    print("\n=== PRIORITIES ===")
    for p in result["priorities"]:
        print("  →", p)
    print(f"\n=== ANNOTATIONS ({len(result['annotations'])}) ===")
    for a in result["annotations"]:
        loc = "" if a["located"] else "  [UNLOCATED]"
        print(f"  [{a['type']}]{loc} \"{a['quote'][:50]}\" — {a['comment']}")
        if a.get("suggestion"):
            print(f"        💡 {a['suggestion']}")


if __name__ == "__main__":
    main()
