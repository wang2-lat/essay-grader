"""Rubric-decomposed, self-consistent AP scorer.

Pipeline (per the 2025 AES literature — rubric-aligned chain-of-thought +
structured component recognition + self-consistency):

  1. The essay is scored against ALL THREE rows in one structured pass, but the
     model must reason in rubric language PER ROW before assigning a number
     (rubric-aligned CoT). This is the AutoSCORE-style component decomposition.
  2. `passes` independent passes are sampled (self-consistency / multi-reader);
     each row's final score is the median across passes.
  3. The official Row B "grammar gate" is enforced DETERMINISTICALLY in code,
     not left to the model: if interfering grammatical/mechanical errors are
     present, Row B is capped at 3.
  4. Total = Row A + Row B + Row C, on the official 0-6 scale.

We reuse the provider-agnostic LLM client from app.core.grader so AP scoring
runs on whatever model the user configured (GLM, DeepSeek, local Ollama, ...).
"""
from __future__ import annotations

import statistics
import time
from typing import Any, Optional

from ..core import grader
from . import anchors as A
from . import annotator as N
from . import rubric as R


def _build_prompt(
    essay: str,
    frq_type: str,
    *,
    prompt_text: Optional[str],
    source_material: Optional[str],
    use_anchors: bool = True,
) -> str:
    rb = R.get_rubric(frq_type)
    rows_block = "\n\n".join(
        R.render_row(row, include_gate=True) for row in rb.rows
    )
    anchor_block = A.anchor_block(frq_type) if use_anchors else ""
    anchor_section = f"\n{anchor_block}\n" if anchor_block else ""

    context = ""
    if prompt_text:
        context += f"\n--- ESSAY PROMPT ---\n{prompt_text.strip()}\n"
    if source_material:
        label = "PROVIDED SOURCES" if frq_type == "synthesis" else "PROVIDED PASSAGE"
        context += f"\n--- {label} ---\n{source_material.strip()}\n"

    template = (
        '{\n'
        '  "row_a": {"score": 0, "thesis_quote": "<the thesis verbatim, or empty>", "rationale": "<why this score, in rubric terms>"},\n'
        '  "row_b": {"score": 0, "evidence_assessment": "<specific vs general; how many sources/claims supported>", '
        '"commentary_assessment": "<does commentary explain HOW evidence supports a line of reasoning?>", '
        '"line_of_reasoning": false, "grammar_interferes": false, "rationale": "<why this score>"},\n'
        '  "row_c": {"score": 0, "sophistication_present": false, "rationale": "<is genuine sophistication PART OF the argument, not just a fancy phrase?>"},\n'
        '  "overall_comment": "<2-4 sentence teacher comment>",\n'
        '  "top_fixes": ["<the single highest-leverage revision>", "<second>", "<third>"]\n'
        '}'
    )

    return f"""You are an experienced, calibrated Reader for the AP English Language and Composition exam, scoring a {rb.label} response on the official 6-point ANALYTIC rubric.

Score by the rubric the way a trained AP Reader does — neither lenient nor artificially harsh. Calibrate your scale to the official anchor essays below.
- Fluent, confident, sophisticated-SOUNDING prose is NOT automatically high. A grammatically clean essay can still earn a low Row B if its commentary does not establish and sustain a line of reasoning.
- Row B: award 4 when the response gives specific evidence for its claims AND consistently explains a line of reasoning (for Rhetorical Analysis, explaining how MULTIPLE rhetorical choices serve the writer's purpose). Reserve 3 for when that explanation is only partial, repetitive, or the reasoning lapses. Do NOT reflexively give 3 to a competent essay that genuinely sustains its reasoning — if it does, 4 is correct.
- Row C (Sophistication) is selective but NOT impossible — a meaningful minority of strong essays earn it, as the anchors show. Award it when sophistication is genuinely part of the argument: a sustained complex/nuanced understanding, situating the analysis in a broader context, or exploring real tensions. Withhold it only for a single fancy phrase or a superficial gesture. Do not reflexively give 0.
- Judge ONLY what the response does with evidence and reasoning, against the descriptors below. Do not reward length or vocabulary for their own sake.

OFFICIAL RUBRIC for {rb.label}:
{rows_block}
{anchor_section}{context}
--- STUDENT RESPONSE ---
{essay.strip()}

INSTRUCTIONS:
1. Row A: Quote the thesis (or note its absence). Decide 0 or 1 strictly by the descriptors.
2. Row B: Catalog the evidence (specific vs general; how many claims/sources are actually supported). Then judge the COMMENTARY: does it merely summarize, relate-without-reasoning, or consistently explain a line of reasoning? For Rhetorical Analysis, also judge whether the response explains how rhetorical CHOICES contribute to the writer's purpose. Decide 0-4. Separately, set "grammar_interferes" to true ONLY if grammatical/mechanical errors actually impede understanding.
3. Row C: Decide 0 or 1. Be stringent.
4. Reason in rubric language BEFORE committing to each number.

Return a JSON object ONLY, exactly these keys, no markdown fences, no extra text:
{template}"""


def _judge_sophistication(
    essay: str,
    frq_type: str,
    *,
    prompt_text: Optional[str],
    source_material: Optional[str],
) -> dict[str, Any]:
    """Dedicated binary judge for Row C (Sophistication).

    Sophistication is the hardest, most subjective row; the main scorer
    systematically refuses to award it. A focused binary decision, grounded in
    the official criteria AND contrastive (earned / not-earned) anchors, judges
    it far more reliably than the buried-in-three-rows instruction.
    """
    rb = R.get_rubric(frq_type)
    crit = R.render_row(rb.sophistication)
    contrast = A.sophistication_block(frq_type) if A.available() else ""
    ctx = ""
    if source_material:
        label = "PROVIDED SOURCES" if frq_type == "synthesis" else "PROVIDED PASSAGE"
        ctx = f"\n--- {label} (context) ---\n{source_material.strip()[:1500]}\n"

    prompt = f"""You are an AP English Language Reader deciding ONE thing: does this {rb.label} response earn the Sophistication point (Row C)?

OFFICIAL CRITERION:
{crit}

How real AP Readers apply it: the point goes to a MEANINGFUL MINORITY of responses — not only "perfect" essays. Award it when the response does ONE of these AS PART OF ITS ARGUMENT and sustains it (not a single sentence):
- develops a genuinely complex or nuanced understanding (e.g. tensions, contradictions, qualifications);
- situates the argument in a broader context and explains its relevance;
- explains the implications or limitations of its analysis;
- sustains a vivid, persuasive, controlled style throughout.
Withhold it for: a single fancy phrase, a tacked-on "bigger picture" sentence, or merely competent analysis with no added complexity.

{contrast}
{ctx}
--- STUDENT RESPONSE ---
{essay.strip()}

Decide. Return JSON only, no fences:
{{"sophistication": 0, "evidence": "<the specific sustained move that earns it, or why it falls short>", "score": 0}}
(set both "sophistication" and "score" to 1 if earned, else 0)"""

    resp = grader._client().chat.completions.create(
        model=grader.current_model(),
        max_tokens=700,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = grader._loads_loose(resp.choices[0].message.content or "")
    val = raw.get("score", raw.get("sophistication", 0))
    try:
        score = 1 if int(round(float(val))) >= 1 else 0
    except (TypeError, ValueError):
        score = 0
    return {"score": score, "rationale": raw.get("evidence", "")}


def _score_once(
    essay: str,
    frq_type: str,
    *,
    prompt_text: Optional[str],
    source_material: Optional[str],
    temperature: float,
    use_anchors: bool,
) -> dict[str, Any]:
    prompt = _build_prompt(
        essay, frq_type, prompt_text=prompt_text,
        source_material=source_material, use_anchors=use_anchors,
    )
    content = _chat(prompt, temperature, grader.max_tokens())
    return grader._loads_loose(content)


def _chat(prompt: str, temperature: float, max_tokens: int) -> str:
    """Single chat call with one retry on transient failure (e.g. timeout).

    The shared client uses max_retries=0 (mute-avoidance), so we retry once here,
    sequentially — this is not a burst, just resilience for long eval runs.
    """
    last: Exception | None = None
    for attempt in range(2):
        try:
            resp = grader._client().chat.completions.create(
                model=grader.current_model(),
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3)
    raise last  # type: ignore[misc]


def _row_score(raw: dict[str, Any], row_key: str, max_pts: int) -> int:
    block = raw.get(row_key) or {}
    val = block.get("score") if isinstance(block, dict) else None
    try:
        n = int(round(float(val)))
    except (TypeError, ValueError):
        n = 0
    return max(0, min(max_pts, n))


def _apply_grammar_gate(raw: dict[str, Any], row_b_score: int) -> tuple[int, bool]:
    """Official hard rule: interfering grammar errors cap Row B at 3."""
    block = raw.get("row_b") or {}
    interferes = bool(block.get("grammar_interferes")) if isinstance(block, dict) else False
    if interferes and row_b_score == 4:
        return 3, True
    return row_b_score, False


def score_essay(
    essay: str,
    frq_type: str = "argument",
    *,
    prompt_text: Optional[str] = None,
    source_material: Optional[str] = None,
    passes: int = 1,
    use_anchors: bool = True,
    dedicated_c: bool = False,  # validated: GLM-4.6 won't award Row C even with a
                                # focused contrastive judge → no gain, costs a call.
                                # Kept available for a stronger judge model.
    annotate: bool = False,     # add span-anchored, rubric-tagged margin notes
                                # (one extra dedicated pass; see app.ap.annotator)
) -> dict[str, Any]:
    """Score one essay. Returns row scores, total, rationales, and metadata.

    passes=1 → fast interactive grading (single call).
    passes>=3 → self-consistency; each row's score is the median across passes
                (use for evaluation / when accuracy matters more than latency).
    """
    if frq_type not in R.FRQ_TYPES:
        raise ValueError(f"unknown FRQ type {frq_type!r}")
    if passes < 1:
        passes = 1

    rb = R.get_rubric(frq_type)
    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    # 0.2 for a single deterministic pass; a bit hotter when sampling for diversity
    temperature = 0.2 if passes == 1 else 0.45

    for _ in range(passes):
        try:
            samples.append(
                _score_once(
                    essay,
                    frq_type,
                    prompt_text=prompt_text,
                    source_material=source_material,
                    temperature=temperature,
                    use_anchors=use_anchors,
                )
            )
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            errors.append(grader._friendly_error(exc))

    if not samples:
        return {"error": errors[0] if errors else "scoring failed", "ok": False}

    a_scores = [_row_score(s, "row_a", 1) for s in samples]
    b_raw = [_row_score(s, "row_b", 4) for s in samples]
    c_scores = [_row_score(s, "row_c", 1) for s in samples]

    a = int(round(statistics.median(a_scores)))
    b = int(round(statistics.median(b_raw)))
    c = int(round(statistics.median(c_scores)))

    # representative pass = the one whose row scores are closest to the medians
    def _closeness(s: dict[str, Any]) -> int:
        return (
            abs(_row_score(s, "row_a", 1) - a)
            + abs(_row_score(s, "row_b", 4) - b)
            + abs(_row_score(s, "row_c", 1) - c)
        )

    rep = min(samples, key=_closeness)
    b, gated = _apply_grammar_gate(rep, b)

    # Dedicated Row C judge overrides the main pass (which is systematically
    # blind to sophistication). Falls back to the main-pass C on error.
    c_rationale = (rep.get("row_c") or {}).get("rationale", "")
    c_source = "main_pass"
    if dedicated_c:
        try:
            cj = _judge_sophistication(
                essay, frq_type,
                prompt_text=prompt_text, source_material=source_material,
            )
            c = cj["score"]
            c_rationale = cj["rationale"] or c_rationale
            c_source = "dedicated_judge"
        except Exception:  # noqa: BLE001 — keep the main-pass C if the judge fails
            pass

    total = a + b + c
    result: dict[str, Any] = {
        "ok": True,
        "frq_type": frq_type,
        "frq_label": rb.label,
        "total": total,
        "max_total": 6,
        "rows": {
            "A_thesis": {
                "score": a,
                "max": 1,
                "quote": (rep.get("row_a") or {}).get("thesis_quote", ""),
                "rationale": (rep.get("row_a") or {}).get("rationale", ""),
            },
            "B_evidence_commentary": {
                "score": b,
                "max": 4,
                "evidence": (rep.get("row_b") or {}).get("evidence_assessment", ""),
                "commentary": (rep.get("row_b") or {}).get("commentary_assessment", ""),
                "line_of_reasoning": bool((rep.get("row_b") or {}).get("line_of_reasoning")),
                "grammar_gate_applied": gated,
                "rationale": (rep.get("row_b") or {}).get("rationale", ""),
            },
            "C_sophistication": {
                "score": c,
                "max": 1,
                "rationale": c_rationale,
                "judged_by": c_source,
            },
        },
        "overall_comment": rep.get("overall_comment", ""),
        "top_fixes": rep.get("top_fixes", []) or [],
        "annotations": [],
        "meta": {
            "model": grader.current_model(),
            "passes": passes,
            "row_score_samples": {"A": a_scores, "B": b_raw, "C": c_scores},
            "errors": errors,
        },
    }

    # Span-anchored margin notes, grounded in the row verdict we just computed.
    # Annotations are additive — they must never turn a successful score into an
    # error, so any failure here degrades to "no notes" instead of raising.
    if annotate:
        try:
            result["annotations"] = N.annotate(
                essay, frq_type, result["rows"],
                prompt_text=prompt_text, source_material=source_material,
                use_anchors=use_anchors,
                errors=result["meta"]["errors"],
            )
        except Exception as exc:  # noqa: BLE001
            result["meta"]["errors"].append(f"annotate: {exc}")

    return result
