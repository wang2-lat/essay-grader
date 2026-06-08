"""The official AP English Language & Composition analytic rubric, encoded.

Every descriptor below is transcribed verbatim from the 2024 College Board
Scoring Guidelines (data/ap/scoring_guidelines_2024_set1_raw.txt). We keep the
three FRQ types separate because Row A and Row B differ per task (e.g.
Rhetorical Analysis requires explaining rhetorical CHOICES; Synthesis requires
evidence from >=3 provided sources).

The total essay score is Row A + Row B + Row C, i.e. 0-6.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FRQ_TYPES = ("synthesis", "rhetorical_analysis", "argument")

FRQ_LABELS = {
    "synthesis": "Synthesis Essay",
    "rhetorical_analysis": "Rhetorical Analysis",
    "argument": "Argument Essay",
}


@dataclass(frozen=True)
class Row:
    """One reporting category of the rubric (A, B, or C)."""

    key: str            # "thesis" | "evidence_commentary" | "sophistication"
    name: str           # human label
    max_points: int     # 1 for A and C, 4 for B
    # descriptor for each integer score, 0..max_points
    descriptors: dict[int, str]
    # "Decision Rules and Scoring Notes" + "Additional Notes" from the guidelines
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Row A — THESIS (0-1). Differs per FRQ.
# --------------------------------------------------------------------------- #
_ROW_A = {
    "synthesis": Row(
        key="thesis",
        name="Thesis",
        max_points=1,
        descriptors={
            0: ("There is no defensible thesis; OR the intended thesis only "
                "restates the prompt; OR provides a summary of the issue with "
                "no apparent or coherent position; OR there is a thesis, but it "
                "does not respond to the prompt."),
            1: ("Responds to the prompt with a thesis that presents a "
                "defensible position."),
        },
        notes=[
            "The thesis may be more than one sentence, provided the sentences "
            "are in close proximity, and may be anywhere within the response.",
            "For a thesis to be defensible, the sources must include at least "
            "minimal evidence that could be used to support it; the student "
            "need not cite that evidence to earn the thesis point.",
        ],
    ),
    "rhetorical_analysis": Row(
        key="thesis",
        name="Thesis",
        max_points=1,
        descriptors={
            0: ("There is no defensible thesis; OR the intended thesis only "
                "restates the prompt; OR provides a summary of the passage with "
                "no apparent or coherent claim; OR there is a thesis, but it "
                "does not respond to the prompt."),
            1: ("Responds to the prompt with a defensible thesis that analyzes "
                "the writer's rhetorical choices."),
        },
        notes=[
            "The thesis may be more than one sentence, provided the sentences "
            "are in close proximity, and may be anywhere within the response.",
            "The thesis may establish a line of reasoning that structures the "
            "essay, but it needn't do so to earn the thesis point.",
        ],
    ),
    "argument": Row(
        key="thesis",
        name="Thesis",
        max_points=1,
        descriptors={
            0: ("There is no defensible thesis; OR the intended thesis only "
                "restates the prompt; OR provides a summary of the issue with "
                "no apparent or coherent position; OR there is a thesis, but it "
                "does not respond to the prompt."),
            1: ("Responds to the prompt with a thesis that presents a "
                "defensible position."),
        },
        notes=[
            "The thesis may be more than one sentence, provided the sentences "
            "are in close proximity, and may be anywhere within the response.",
        ],
    ),
}


# --------------------------------------------------------------------------- #
# Row B — EVIDENCE AND COMMENTARY (0-4). Differs per FRQ.
# --------------------------------------------------------------------------- #
_ROW_B = {
    "synthesis": Row(
        key="evidence_commentary",
        name="Evidence and Commentary",
        max_points=4,
        descriptors={
            0: ("Simply restates thesis (if present), repeats provided "
                "information, or references fewer than two of the provided "
                "sources."),
            1: ("EVIDENCE: Provides evidence from or references at least two of "
                "the provided sources. AND COMMENTARY: Summarizes the evidence "
                "but does not explain how the evidence supports the student's "
                "argument."),
            2: ("EVIDENCE: Provides evidence from or references at least three "
                "of the provided sources. AND COMMENTARY: Explains how some of "
                "the evidence relates to the student's argument, but no line of "
                "reasoning is established, or the line of reasoning is faulty."),
            3: ("EVIDENCE: Provides specific evidence from at least three of the "
                "provided sources to support all claims in a line of reasoning. "
                "AND COMMENTARY: Explains how some of the evidence supports a "
                "line of reasoning."),
            4: ("EVIDENCE: Provides specific evidence from at least three of the "
                "provided sources to support all claims in a line of reasoning. "
                "AND COMMENTARY: Consistently explains how the evidence supports "
                "a line of reasoning."),
        },
    ),
    "rhetorical_analysis": Row(
        key="evidence_commentary",
        name="Evidence and Commentary",
        max_points=4,
        descriptors={
            0: ("Simply restates thesis (if present), repeats provided "
                "information, or offers information irrelevant to the prompt."),
            1: ("EVIDENCE: Provides evidence that is mostly general. AND "
                "COMMENTARY: Summarizes the evidence but does not explain how "
                "the evidence supports the student's argument."),
            2: ("EVIDENCE: Provides some specific, relevant evidence. AND "
                "COMMENTARY: Explains how some of the evidence relates to the "
                "student's argument, but no line of reasoning is established, or "
                "the line of reasoning is faulty."),
            3: ("EVIDENCE: Provides specific evidence to support all claims in a "
                "line of reasoning. AND COMMENTARY: Explains how some of the "
                "evidence supports a line of reasoning, AND explains how at "
                "least one rhetorical choice in the passage contributes to the "
                "writer's argument, purpose, or message."),
            4: ("EVIDENCE: Provides specific evidence to support all claims in a "
                "line of reasoning. AND COMMENTARY: Consistently explains how "
                "the evidence supports a line of reasoning, AND explains how "
                "multiple rhetorical choices in the passage contribute to the "
                "writer's argument, purpose, or message."),
        },
        notes=[
            "To earn the fourth point, the response may observe multiple "
            "instances of the same rhetorical choice if each instance further "
            "contributes to the argument, purpose, or message of the passage.",
        ],
    ),
    "argument": Row(
        key="evidence_commentary",
        name="Evidence and Commentary",
        max_points=4,
        descriptors={
            0: ("Simply restates thesis (if present), repeats provided "
                "information, or offers information irrelevant to the prompt."),
            1: ("EVIDENCE: Provides evidence that is mostly general. AND "
                "COMMENTARY: Summarizes the evidence but does not explain how "
                "the evidence supports the argument."),
            2: ("EVIDENCE: Provides some specific, relevant evidence. AND "
                "COMMENTARY: Explains how some of the evidence relates to the "
                "student's argument, but no line of reasoning is established, or "
                "the line of reasoning is faulty."),
            3: ("EVIDENCE: Provides specific evidence to support all claims in a "
                "line of reasoning. AND COMMENTARY: Explains how some of the "
                "evidence supports a line of reasoning."),
            4: ("EVIDENCE: Provides specific evidence to support all claims in a "
                "line of reasoning. AND COMMENTARY: Consistently explains how "
                "the evidence supports a line of reasoning."),
        },
    ),
}

# Applies to Row B for ALL FRQ types (official "Additional Notes"):
ROW_B_GRAMMAR_GATE = (
    "Writing that suffers from grammatical and/or mechanical errors that "
    "interfere with communication cannot earn the fourth point in this row."
)


# --------------------------------------------------------------------------- #
# Row C — SOPHISTICATION (0-1). Shared wording across all three FRQs.
# --------------------------------------------------------------------------- #
def _row_c(situation: str) -> Row:
    return Row(
        key="sophistication",
        name="Sophistication",
        max_points=1,
        descriptors={
            0: "Does not meet the criteria for one point.",
            1: (f"Demonstrates sophistication of thought and/or develops a "
                f"complex understanding of {situation}."),
        },
        notes=[
            "This point should be awarded only if the sophistication of thought "
            "or complex understanding is part of the student's argument, not "
            "merely a phrase or reference.",
            "Responses may earn this point by (one or more of): identifying and "
            "exploring complexities or tensions; situating the argument within a "
            "broader context; explaining the relevance of purpose, implications, "
            "or limitations; or employing a style that is consistently vivid and "
            "persuasive.",
        ],
    )


_ROW_C = {
    "synthesis": _row_c("the ideas developed in the response"),
    "rhetorical_analysis": _row_c("the rhetorical situation"),
    "argument": _row_c("the ideas developed in the response"),
}


@dataclass(frozen=True)
class Rubric:
    frq_type: str
    label: str
    thesis: Row
    evidence_commentary: Row
    sophistication: Row

    @property
    def rows(self) -> list[Row]:
        return [self.thesis, self.evidence_commentary, self.sophistication]


def get_rubric(frq_type: str) -> Rubric:
    if frq_type not in FRQ_TYPES:
        raise ValueError(
            f"unknown FRQ type {frq_type!r}; expected one of {FRQ_TYPES}"
        )
    return Rubric(
        frq_type=frq_type,
        label=FRQ_LABELS[frq_type],
        thesis=_ROW_A[frq_type],
        evidence_commentary=_ROW_B[frq_type],
        sophistication=_ROW_C[frq_type],
    )


def render_row(row: Row, *, include_gate: bool = False) -> str:
    """Plain-text rendering of a single row for use inside an LLM prompt."""
    lines = [f"{row.name} (0-{row.max_points} points):"]
    for score in range(row.max_points + 1):
        lines.append(f"  [{score}] {row.descriptors[score]}")
    for note in row.notes:
        lines.append(f"  NOTE: {note}")
    if include_gate and row.key == "evidence_commentary":
        lines.append(f"  HARD RULE: {ROW_B_GRAMMAR_GATE}")
    return "\n".join(lines)
