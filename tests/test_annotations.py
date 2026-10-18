"""Quote location: margin notes are trusted only if their quote is in the essay."""
from __future__ import annotations

from app.core import grader
from app.core.rubric import ANNOTATION_TYPES

TEXT = "The first sentence is here.  It   has spacing.\nThe end of the essay."


def locate(raw, default="style"):
    return grader.locate_annotations(TEXT, raw, ANNOTATION_TYPES, default_type=default)


def test_exact_quote_gets_char_span():
    [a] = locate([{"quote": "It   has spacing.", "type": "grammar", "comment": "c"}])
    assert a["located"] is True
    assert TEXT[a["start"]:a["end"]] == "It   has spacing."


def test_quote_whitespace_is_stripped_before_matching():
    [a] = locate([{"quote": "  The end of the essay.  ", "type": "grammar"}])
    assert a["quote"] == "The end of the essay."
    assert a["located"] is True
    assert TEXT[a["start"]:a["end"]] == a["quote"]


def test_collapsed_whitespace_still_locates_start():
    # The model wrote single spaces / no newline; the essay has runs of whitespace.
    [a] = locate([{"quote": "here. It has spacing.", "type": "grammar"}])
    assert a["located"] is True
    assert a["start"] == TEXT.index("here.")


def test_quote_not_in_essay_is_kept_but_flagged_unlocated():
    [a] = locate([{"quote": "a sentence the student never wrote", "type": "grammar",
                   "comment": "keep me"}])
    assert a["located"] is False
    assert (a["start"], a["end"]) == (-1, -1)
    assert a["comment"] == "keep me"


def test_empty_quote_is_unlocated():
    [a] = locate([{"quote": "", "type": "grammar"}])
    assert a["located"] is False


def test_results_sorted_by_position_with_unlocated_last():
    out = locate([
        {"quote": "The end of the essay.", "type": "grammar"},
        {"quote": "missing", "type": "grammar"},
        {"quote": "The first sentence", "type": "grammar"},
    ])
    assert [a["quote"] for a in out] == ["The first sentence", "The end of the essay.", "missing"]


def test_unknown_type_falls_back_to_default_and_fields_are_filled():
    [a] = locate([{"quote": "The first sentence", "type": "vibes"}], default="style")
    assert a["type"] == "style"
    assert a["comment"] == "" and a["suggestion"] == ""


def test_non_dict_entries_and_none_are_ignored():
    assert locate(None) == []
    out = locate(["just a string", 42, {"quote": "The first sentence", "type": "grammar"}])
    assert len(out) == 1


def test_extra_keys_are_preserved():
    [a] = locate([{"quote": "The first sentence", "type": "grammar", "row": "B"}])
    assert a["row"] == "B"


# ------------------------------------------------- ELLIPSE grader end to end (mocked)

def test_grade_essay_clamps_scores_and_locates_quotes(fake_llm):
    fake_llm.queue({
        "rubric_check": {},
        "scores": {"cohesion": 6, "syntax": 2.3, "vocabulary": 0, "phraseology": "3.5",
                   "grammar": None, "conventions": 4, "overall": 3},
        "summary": "s", "strengths": ["good", ""], "priorities": ["fix"],
        "annotations": [
            {"quote": "The end of the essay.", "type": "conventions", "comment": "c"},
            {"quote": "not there", "type": "grammar", "comment": "c"},
        ],
    })
    result = grader.grade_essay(essay_text=TEXT)
    s = result["scores"]
    assert s["cohesion"] == 5.0          # clamped to SCALE_MAX
    assert s["syntax"] == 2.5            # rounded to 0.5 steps
    assert s["vocabulary"] == 1.0        # clamped to SCALE_MIN
    assert s["phraseology"] == 3.5
    assert s["grammar"] == 3.0           # missing -> falls back to overall
    assert result["strengths"] == ["good"]
    located = [a["located"] for a in result["annotations"]]
    assert located == [True, False]
    assert len(fake_llm.calls) == 1


def test_grade_essay_derives_overall_when_missing(fake_llm):
    fake_llm.queue({"scores": {"cohesion": 2, "syntax": 3, "vocabulary": 4,
                               "phraseology": 3, "grammar": 3, "conventions": 3}})
    result = grader.grade_essay(essay_text=TEXT)
    assert result["scores"]["overall"] == 3.0


def test_grade_essay_rejects_empty_text_without_calling_model(fake_llm):
    import pytest

    with pytest.raises(ValueError):
        grader.grade_essay(essay_text="   ")
    assert fake_llm.calls == []
