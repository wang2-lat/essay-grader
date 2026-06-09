"""Dedicated, rubric-grounded margin-annotation pass for the AP scorer.

The main scorer (`app.ap.scorer`) decides the three row scores. This module adds
the *targeted* layer the user actually marks a paper with: Google-Doc-style
margin notes anchored to specific spans of the student's text — "this is your
thesis but it only restates the prompt", "good specific evidence here", "this
sentence summarizes the source instead of explaining how it supports your line
of reasoning".

It is built the SAME way the scorer was "trained":

  1. RUBRIC-DECOMPOSED — every note is tagged to the rubric row it speaks to
     (A thesis / B evidence / B commentary / B reasoning / C sophistication /
     grammar gate), and must be phrased in rubric language, not vibes.
  2. DIAGNOSIS-GROUNDED — the pass receives the row scores + rationales the
     scorer already produced, so the inline notes are CONSISTENT with the grade
     (we don't praise commentary in the margin and then score Row B a 2).
  3. ANCHOR-CALIBRATED — reuses the same official calibration anchors so the
     bar for "good evidence" matches the bar the score was set against.
  4. DETERMINISTICALLY VERIFIED — every quote is resolved back to a real char
     span by `grader.locate_annotations`; the model proposes, the code verifies.
     This is the annotation analog of the scorer's in-code grammar gate.

Kept as a separate pass (not folded into the scoring call) for the same reason
Row C has its own judge: a focused task with its own instructions produces far
better margin notes than one buried inside the three-row scoring instruction.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..core import grader
from . import anchors as A
from . import rubric as R

# Annotation types, each mapped to the rubric row it reports on. Keeping these in
# rubric language (not generic "style"/"clarity") is what makes the feedback
# actionable against the official 6-point scale.
AP_ANNOTATION_TYPES = [
    "thesis",          # Row A — the defensible position / claim
    "evidence",        # Row B — the specificity & relevance of support
    "commentary",      # Row B — explaining HOW evidence supports the argument
    "reasoning",       # Row B — the line of reasoning / its structure
    "sophistication",  # Row C — complexity, tension, broader context, style
    "grammar",         # Row B gate — errors that interfere with communication
    "praise",          # reinforce a move the student got right
]

_TYPE_TO_ROW = {
    "thesis": "A",
    "evidence": "B",
    "commentary": "B",
    "reasoning": "B",
    "sophistication": "C",
    "grammar": "B",
    "praise": "-",
}

_TEMPLATE = (
    '{\n'
    '  "annotations": [\n'
    '    {"quote": "<short EXACT substring from the essay, <12 words>", '
    '"type": "<one of the allowed types>", '
    '"comment": "<margin note spoken TO the student: specific, kind, names the rubric issue>", '
    '"suggestion": "<a concrete rewrite or next move, or empty string>"},\n'
    '    {"quote": "<another EXACT substring>", "type": "praise", '
    '"comment": "<a genuine strength, named in rubric terms — REQUIRED: at least one praise note>", '
    '"suggestion": ""}\n'
    '  ]\n'
    '}'
)


def _diagnosis_block(rows: dict[str, Any]) -> str:
    """Render the scorer's own row verdicts so the notes stay consistent with them."""
    a = rows.get("A_thesis", {})
    b = rows.get("B_evidence_commentary", {})
    c = rows.get("C_sophistication", {})
    parts = [
        "YOUR OWN SCORING VERDICT on this essay (make every margin note consistent "
        "with it — do not praise in the margin what you penalized in the score, or "
        "vice versa):",
        f"- Row A (Thesis) = {a.get('score')}/1 — {a.get('rationale','')}".rstrip(),
        f"- Row B (Evidence & Commentary) = {b.get('score')}/4 — "
        f"evidence: {b.get('evidence','')} commentary: {b.get('commentary','')} "
        f"{b.get('rationale','')}".rstrip(),
        f"- Row C (Sophistication) = {c.get('score')}/1 — {c.get('rationale','')}".rstrip(),
    ]
    return "\n".join(parts)


def _build_prompt(
    essay: str,
    frq_type: str,
    rows: dict[str, Any],
    *,
    prompt_text: Optional[str],
    source_material: Optional[str],
    use_anchors: bool,
) -> str:
    rb = R.get_rubric(frq_type)
    rows_block = "\n\n".join(R.render_row(row, include_gate=True) for row in rb.rows)
    anchor_block = A.anchor_block(frq_type) if use_anchors and A.available() else ""
    anchor_section = f"\n{anchor_block}\n" if anchor_block else ""

    context = ""
    if prompt_text:
        context += f"\n--- ESSAY PROMPT ---\n{prompt_text.strip()}\n"
    if source_material:
        label = "PROVIDED SOURCES" if frq_type == "synthesis" else "PROVIDED PASSAGE"
        context += f"\n--- {label} ---\n{source_material.strip()[:2000]}\n"

    types = ", ".join(AP_ANNOTATION_TYPES)

    return f"""You are an experienced AP English Language Reader marking up a {rb.label} \
response by hand — leaving margin notes the way a teacher annotates a paper in Google Docs.

You have ALREADY scored this essay on the official 6-point analytic rubric. Now produce \
the targeted, span-level feedback that explains the score and shows the student exactly \
where and how to improve.

OFFICIAL RUBRIC for {rb.label}:
{rows_block}
{anchor_section}
{_diagnosis_block(rows)}
{context}
--- STUDENT RESPONSE ---
{essay.strip()}

HOW TO ANNOTATE — like marking up a paper by hand:
- Produce 6 to 12 notes, SPREAD across the whole response (beginning, middle, end), not clustered.
- Each note targets ONE specific span. "quote" MUST be copied character-for-character from \
the essay above — keep it SHORT (under 12 words) so it matches exactly. Do not paraphrase or \
fix typos inside the quote.
- Tag each note with exactly one "type" from: {types}. Choose the type by which rubric row \
the note speaks to (thesis→Row A; evidence/commentary/reasoning→Row B; sophistication→Row C; \
grammar→the Row B grammar gate; praise→a move done well).
- "comment" speaks directly to the student: specific, kind, and phrased in rubric terms — name \
what the rubric wants and how this span falls short or succeeds. Never vague ("be clearer", "good job").
- "suggestion" gives a concrete rewrite or next move (or "" if a rewrite doesn't apply, e.g. for praise).
- REQUIRED, not optional: at least ONE note must have type "praise". Even a weak essay does \
something right — a defensible thesis, one specific piece of evidence, a clear transition. \
Students learn from seeing what worked; a markup with zero praise is incomplete.
- Anchor the notes to what would actually move a row score: e.g. if Row B is capped because \
commentary only summarizes, point to a specific summarizing sentence and show the line-of-reasoning \
explanation it's missing.
- Before finishing, re-read each "quote" and confirm it appears verbatim in the student response.

Return a JSON object ONLY — exactly this shape, no markdown fences, no commentary, no <think>:
{_TEMPLATE}"""


def annotate(
    essay: str,
    frq_type: str,
    rows: dict[str, Any],
    *,
    prompt_text: Optional[str] = None,
    source_material: Optional[str] = None,
    use_anchors: bool = True,
    errors: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Produce verified, rubric-tagged margin annotations for one AP response.

    `rows` is the `result["rows"]` block from `scorer.score_essay`, used to keep
    the inline notes consistent with the row scores. Returns a list of
    annotations, each with quote/type/row/comment/suggestion and the resolved
    char span (start/end/located) from `grader.locate_annotations`.

    Returns [] on any failure — annotations are additive, never fatal to scoring.
    Pass an `errors` list to find out WHY it came back empty (the scorer wires
    this to result["meta"]["errors"]); silent [] with no trace is undebuggable.
    """
    if frq_type not in R.FRQ_TYPES:
        raise ValueError(f"unknown FRQ type {frq_type!r}")

    prompt = _build_prompt(
        essay, frq_type, rows,
        prompt_text=prompt_text, source_material=source_material,
        use_anchors=use_anchors,
    )
    # One retry on transient failure, mirroring scorer._chat: the shared client
    # uses max_retries=0, so a single API blip would otherwise yield zero notes.
    # The 8s pause matters: this call fires right after the scoring call(s), so
    # the most common failure is a burst rate-limit — 3s is usually still inside
    # the limit window. Annotations are additive — on genuine failure we return
    # [] (with the reason recorded in `errors`) rather than break the score.
    raw: Any = {}
    for attempt in range(2):
        try:
            resp = grader._client().chat.completions.create(
                model=grader.current_model(),
                max_tokens=grader.max_tokens(),
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = grader._loads_loose(resp.choices[0].message.content or "")
            break
        except Exception as exc:  # noqa: BLE001 — never let annotation failure break the score
            if attempt == 0:
                time.sleep(8)
                continue
            if errors is not None:
                errors.append(f"annotate: {exc}")
            return []

    if not isinstance(raw, dict):  # model returned a bare list / scalar JSON
        raw = {"annotations": raw if isinstance(raw, list) else []}

    located = grader.locate_annotations(
        essay, raw.get("annotations", []), AP_ANNOTATION_TYPES, default_type="commentary",
    )
    # Attach the rubric row each note reports on (handy for the UI / validation).
    for a in located:
        a["row"] = _TYPE_TO_ROW.get(a.get("type"), "-")
    return located
