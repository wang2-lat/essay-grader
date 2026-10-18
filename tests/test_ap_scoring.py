"""AP scorer: row clamping, the Row B grammar gate, totals, self-consistency.

All model output is faked (see conftest.fake_llm); nothing leaves the process.
"""
from __future__ import annotations

import pytest

from app.ap import scorer

ESSAY = (
    "Technology should be limited in classrooms. Students who rely on screens "
    "lose focus, as the 2019 survey in Source A shows. Therefore schools must "
    "set clear limits."
)


def ap_reply(a=1, b=3, c=0, grammar_interferes=False, **extra):
    reply = {
        "row_a": {"score": a, "thesis_quote": "Technology should be limited in classrooms.",
                  "rationale": "defensible"},
        "row_b": {"score": b, "evidence_assessment": "specific", "commentary_assessment": "ok",
                  "line_of_reasoning": True, "grammar_interferes": grammar_interferes,
                  "rationale": "r"},
        "row_c": {"score": c, "sophistication_present": bool(c), "rationale": "c"},
        "overall_comment": "Solid.",
        "top_fixes": ["Explain how the evidence supports the claim."],
    }
    reply.update(extra)
    return reply


# ----------------------------------------------------------------- grammar gate

def test_grammar_gate_caps_row_b_four_to_three():
    assert scorer._apply_grammar_gate({"row_b": {"grammar_interferes": True}}, 4) == (3, True)


@pytest.mark.parametrize("score", [0, 1, 2, 3])
def test_grammar_gate_leaves_scores_below_four_alone(score):
    assert scorer._apply_grammar_gate({"row_b": {"grammar_interferes": True}}, score) == (score, False)


def test_grammar_gate_not_applied_without_interfering_errors():
    assert scorer._apply_grammar_gate({"row_b": {"grammar_interferes": False}}, 4) == (4, False)
    assert scorer._apply_grammar_gate({}, 4) == (4, False)
    assert scorer._apply_grammar_gate({"row_b": "not a dict"}, 4) == (4, False)


# ----------------------------------------------------------------- row clamping

@pytest.mark.parametrize(
    "raw, max_pts, expected",
    [
        ({"row_b": {"score": 7}}, 4, 4),        # above max -> max
        ({"row_b": {"score": -2}}, 4, 0),       # below 0 -> 0
        ({"row_b": {"score": "3"}}, 4, 3),      # numeric string
        ({"row_b": {"score": 2.6}}, 4, 3),      # rounds
        ({"row_b": {"score": None}}, 4, 0),     # missing -> 0
        ({"row_b": {"score": "abc"}}, 4, 0),    # garbage -> 0
        ({"row_b": 3}, 4, 0),                   # block not a dict -> 0
        ({}, 4, 0),                             # row missing -> 0
        ({"row_a": {"score": 5}}, 1, 1),        # Row A capped at 1
    ],
)
def test_row_score_clamps_to_rubric_range(raw, max_pts, expected):
    key = next(iter(raw), "row_b")
    assert scorer._row_score(raw, key, max_pts) == expected


# ----------------------------------------------------------------- score_essay

def test_total_is_sum_of_rows_on_six_point_scale(fake_llm):
    fake_llm.queue(ap_reply(a=1, b=3, c=1))
    result = scorer.score_essay(ESSAY, "argument")
    assert result["ok"] is True
    assert result["max_total"] == 6
    rows = result["rows"]
    assert (rows["A_thesis"]["score"], rows["B_evidence_commentary"]["score"],
            rows["C_sophistication"]["score"]) == (1, 3, 1)
    assert result["total"] == 5
    assert rows["B_evidence_commentary"]["grammar_gate_applied"] is False
    assert len(fake_llm.calls) == 1


def test_grammar_gate_is_enforced_in_code_not_by_the_model(fake_llm):
    # The model says Row B = 4 but also that grammar interferes: code must cap it.
    fake_llm.queue(ap_reply(a=1, b=4, c=0, grammar_interferes=True))
    result = scorer.score_essay(ESSAY, "rhetorical_analysis")
    b = result["rows"]["B_evidence_commentary"]
    assert b["score"] == 3
    assert b["grammar_gate_applied"] is True
    assert result["total"] == 4


def test_out_of_range_model_scores_are_clamped(fake_llm):
    fake_llm.queue(ap_reply(a=3, b=9, c=2))
    result = scorer.score_essay(ESSAY, "synthesis")
    assert result["total"] == 6
    assert result["rows"]["A_thesis"]["score"] == 1
    assert result["rows"]["B_evidence_commentary"]["score"] == 4


def test_multiple_passes_use_the_median_per_row(fake_llm):
    fake_llm.queue(ap_reply(b=2), ap_reply(b=4), ap_reply(b=3))
    result = scorer.score_essay(ESSAY, "argument", passes=3)
    assert len(fake_llm.calls) == 3
    assert result["rows"]["B_evidence_commentary"]["score"] == 3
    assert result["meta"]["row_score_samples"]["B"] == [2, 4, 3]
    assert result["meta"]["passes"] == 3


def test_model_output_with_think_block_and_fences_is_parsed(fake_llm):
    import json

    wrapped = "<think>reasoning...</think>\n```json\n" + json.dumps(ap_reply(b=2)) + "\n```"
    fake_llm.queue(wrapped)
    result = scorer.score_essay(ESSAY, "argument")
    assert result["ok"] is True
    assert result["rows"]["B_evidence_commentary"]["score"] == 2


def test_unknown_frq_type_is_rejected_before_any_model_call(fake_llm):
    with pytest.raises(ValueError):
        scorer.score_essay(ESSAY, "poetry")
    assert fake_llm.calls == []


def test_all_passes_failing_returns_error_not_a_score(fake_llm):
    # _chat retries once per pass, so one pass = two failed calls.
    fake_llm.queue(RuntimeError("connection reset"), RuntimeError("connection reset"))
    result = scorer.score_essay(ESSAY, "argument")
    assert result["ok"] is False
    assert "error" in result
    assert "total" not in result


def test_one_transient_failure_is_retried(fake_llm):
    fake_llm.queue(RuntimeError("timeout"), ap_reply(b=3))
    result = scorer.score_essay(ESSAY, "argument")
    assert result["ok"] is True
    assert len(fake_llm.calls) == 2


# ----------------------------------------------------------------- annotations path

def test_annotate_adds_located_rubric_tagged_notes(fake_llm):
    fake_llm.queue(
        ap_reply(b=3),
        {"annotations": [
            {"quote": "Therefore schools must set clear limits.", "type": "reasoning",
             "comment": "Explain why.", "suggestion": ""},
            {"quote": "Technology should be limited in classrooms.", "type": "thesis",
             "comment": "Clear thesis.", "suggestion": ""},
            {"quote": "this sentence is not in the essay", "type": "praise",
             "comment": "x", "suggestion": ""},
        ]},
    )
    result = scorer.score_essay(ESSAY, "argument", annotate=True)
    notes = result["annotations"]
    assert [n["type"] for n in notes] == ["thesis", "reasoning", "praise"]  # sorted by position
    assert [n["row"] for n in notes] == ["A", "B", "-"]
    thesis = notes[0]
    assert thesis["located"] is True
    assert ESSAY[thesis["start"]:thesis["end"]] == thesis["quote"]
    assert notes[-1]["located"] is False and notes[-1]["start"] == -1


def test_annotation_failure_never_breaks_the_score(fake_llm):
    # score ok, then the annotator's two attempts both fail
    fake_llm.queue(ap_reply(b=3), RuntimeError("rate limit"), RuntimeError("rate limit"))
    result = scorer.score_essay(ESSAY, "argument", annotate=True)
    assert result["ok"] is True
    assert result["total"] == 4
    assert result["annotations"] == []
    assert any(e.startswith("annotate:") for e in result["meta"]["errors"])
