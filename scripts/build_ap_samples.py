"""Build the official AP sample dataset from AP Central scored-response PDFs.

Each PDF (data/ap/samples_raw/ap24-apc-english-language-q{1,2,3}-set-{1,2}.pdf)
contains, for ~3 student responses:
  - the student essay as SCANNED HANDWRITTEN IMAGES (no text layer), and
  - official scoring commentary stating "Score: A-B-C" + a rationale that quotes
    the essay verbatim.

We:
  1. parse each sample's official Row A/B/C score + commentary,
  2. transcribe the handwritten essay image(s) with a vision LLM,
  3. VERIFY the transcription by checking that the verbatim quotes cited in the
     official commentary actually appear in our transcription (this guards
     against OCR hallucination — a transcription that doesn't contain the
     officially-quoted phrases is rejected),
  4. write data/ap/samples.json  ->  [{frq_type, sample_id, scores, essay_text,
     commentary, verified, quote_hits, ...}].

Vision + grading reuse the user's configured provider (app.core.grader); the
vision model defaults to glm-4.5v (Zhipu) and can be overridden via
GRADER_VISION_MODEL.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from app.core import grader  # noqa: E402

RAW = _ROOT / "data" / "ap" / "samples_raw"
TRANSCRIPTS = RAW / "transcripts"
OUT = _ROOT / "data" / "ap" / "samples.json"
VISION_MODEL = os.environ.get("GRADER_VISION_MODEL", "glm-4.5v")

FRQ_BY_Q = {"q1": "synthesis", "q2": "rhetorical_analysis", "q3": "argument"}


def _norm(s: str) -> str:
    """Lowercase, collapse whitespace, normalize quotes/dashes for fuzzy match."""
    s = s.lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip()


def parse_pdf(pdf: Path):
    r = PdfReader(str(pdf))
    if r.is_encrypted:
        r.decrypt("")
    pages = [(p.extract_text() or "") for p in r.pages]
    full = "\n".join(pages)

    # --- commentary: split on "Sample: <ID>" then read "Score: A-B-C" ---
    samples: dict[str, dict] = {}
    blocks = re.split(r"Sample:\s*([0-9][A-Z])\b", full)
    # blocks = [pre, id1, body1, id2, body2, ...]
    for i in range(1, len(blocks), 2):
        sid = blocks[i]
        body = blocks[i + 1]
        m = re.search(r"Score:\s*(\d)\s*[-–]\s*(\d)\s*[-–]\s*(\d)", body)
        if not m:
            continue
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        samples.setdefault(sid, {})
        samples[sid].update(
            {"scores": {"A": a, "B": b, "C": c, "total": a + b + c},
             "commentary": body.strip()[:4000]}
        )

    # --- essay images: pages titled "Sample <ID> (n of m)" ---
    img_pages: dict[str, list[int]] = {}
    for idx, txt in enumerate(pages):
        m = re.search(r"Sample\s+([0-9][A-Z])\s*\((\d+)\s+of\s+(\d+)\)", txt)
        if m:
            img_pages.setdefault(m.group(1), []).append(idx)
    return r, samples, img_pages


def transcribe_pages(pdf_path: Path, page_idxs: list[int], cache_key: str) -> str:
    """Rasterize each sample page with PyMuPDF and vision-transcribe it.

    Rasterizing the whole page (rather than pulling embedded images) works for
    both handwritten scans (set-1) and typed responses drawn directly on the
    page (set-2, which expose no /XObject image to pypdf).
    """
    import fitz  # pymupdf

    cache = TRANSCRIPTS / f"{cache_key}.txt"
    if cache.exists() and len(cache.read_text(encoding="utf-8").strip()) >= 200:
        return cache.read_text(encoding="utf-8")
    doc = fitz.open(str(pdf_path))
    parts = []
    for pi in page_idxs:
        png = doc[pi].get_pixmap(dpi=180).tobytes("png")
        b64 = base64.b64encode(png).decode()
        resp = grader._client().chat.completions.create(
            model=VISION_MODEL,
            max_tokens=2200,
            temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": (
                    "This is one page of a student's AP English essay. Transcribe "
                    "ALL of the student's essay text VERBATIM to plain text. "
                    "Preserve exact wording, spelling, and punctuation; do not "
                    "correct errors. Ignore the page header label like "
                    "'Sample 2A (1 of 1)'. Output ONLY the transcription.")},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
        )
        parts.append((resp.choices[0].message.content or "").strip())
        time.sleep(1.2)  # gentle on the provider (mute-avoidance)
    text = "\n".join(parts).strip()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def verify(transcript: str, commentary: str) -> tuple[bool, int, int]:
    """How many verbatim quotes from the official commentary appear in the
    transcript. Tolerant of minor OCR drift: a quote counts as a hit if ANY
    contiguous ~24-char slice of it is found in the transcript."""
    quotes = re.findall(r"[“\"]([^”\"]{12,160})[”\"]", commentary)
    if not quotes:
        return False, 0, 0
    nt = _norm(transcript)
    hits = 0
    for q in quotes:
        nq = _norm(q)
        win = 24
        found = nq in nt or any(
            nq[i:i + win] in nt for i in range(0, max(1, len(nq) - win), 6)
        )
        hits += 1 if found else 0
    # verified if >=2 quotes match OR at least a third of the cited quotes
    ok = hits >= 2 or (len(quotes) and hits / len(quotes) >= 0.34)
    return ok, hits, len(quotes)


def main() -> int:
    records = []
    for pdf in sorted(RAW.glob("ap2*-apc-english-language-q*.pdf")):
        m = re.search(r"ap(\d{2})-apc-english-language-(q[123])(?:-set-(\d))?", pdf.name)
        if not m:
            continue
        year = "20" + m.group(1)
        frq = FRQ_BY_Q[m.group(2)]
        setn = m.group(3) or "0"   # 2021/2022 single-file releases have no set
        reader, samples, img_pages = parse_pdf(pdf)
        print(f"\n=== {pdf.name}  ({year} {frq}, set {setn}) — samples: {sorted(samples)} ===")
        for sid, info in sorted(samples.items()):
            pages = img_pages.get(sid, [])
            if not pages:
                print(f"  {sid}: no image pages found, skip")
                continue
            # keep 2024 cache keys backward-compatible (already transcribed)
            key = (f"{frq}_set{setn}_{sid}" if year == "2024"
                   else f"{frq}_{year}_set{setn}_{sid}")
            text = transcribe_pages(pdf, pages, key)
            ok, hits, total_q = verify(text, info["commentary"])
            print(f"  {sid}: score {info['scores']['A']}-{info['scores']['B']}-{info['scores']['C']}"
                  f"  | {len(text)} chars | quotes {hits}/{total_q} "
                  f"| {'VERIFIED' if ok else 'unverified'}")
            records.append({
                "frq_type": frq, "year": year, "set": setn, "sample_id": sid,
                "scores": info["scores"], "essay_text": text,
                "commentary": info["commentary"], "verified": ok,
                "quote_hits": hits, "quote_total": total_q,
                "source_pdf": pdf.name,
            })
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    v = sum(1 for r in records if r["verified"])
    print(f"\nWROTE {OUT}  —  {len(records)} samples, {v} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
