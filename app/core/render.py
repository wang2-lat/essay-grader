"""Render an essay with inline annotation highlights (server-side)."""
from __future__ import annotations

from html import escape
from typing import Any


def annotated_html(essay_text: str, annotations: list[dict[str, Any]]) -> str:
    """Return HTML for the essay with located annotations wrapped in <mark>.

    Annotations carry char offsets (start/end) from the grader. Overlapping or
    unlocated annotations are skipped for inline marking (they still appear in
    the side panel). Each mark links to its panel note via a shared index.
    """
    located = [a for a in annotations if a.get("located") and a.get("start", -1) >= 0]
    located.sort(key=lambda a: a["start"])

    # Drop overlaps — keep the earliest, skip any that start before prev end.
    spans = []
    last_end = -1
    for a in located:
        if a["start"] < last_end:
            continue
        spans.append(a)
        last_end = a["end"]

    pieces: list[str] = []
    cursor = 0
    for a in spans:
        idx = a["_idx"]
        start, end = a["start"], a["end"]
        if start > cursor:
            pieces.append(escape(essay_text[cursor:start]))
        seg = escape(essay_text[start:end])
        atype = escape(a.get("type", "note"))
        pieces.append(
            f'<mark class="ann ann-{atype}" data-idx="{idx}" '
            f'id="mark-{idx}" tabindex="0">{seg}'
            f'<sup class="ann-num">{idx + 1}</sup></mark>'
        )
        cursor = end
    if cursor < len(essay_text):
        pieces.append(escape(essay_text[cursor:]))

    html = "".join(pieces).replace("\n", "<br>\n")
    return html
