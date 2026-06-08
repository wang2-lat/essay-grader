"""The grading engine.

Wraps an OpenAI-compatible chat model (DeepSeek via a local reverse proxy) with
the ELLIPSE rubric, professionally rated calibration anchors, and a forced
function-call so every evaluation comes back with analytic scores, inline
teacher-style annotations, and actionable revision guidance.

Configured purely via env vars so the provider can be swapped without code
changes:
    GRADER_BASE_URL   OpenAI-compatible endpoint (default: local DeepSeek proxy)
    GRADER_API_KEY    bearer key for that endpoint
    GRADER_MODEL      model id (default: deepseek-default)
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from .rubric import (
    ANNOTATION_TYPES,
    DIMENSIONS,
    SCALE_MAX,
    SCALE_MIN,
    rubric_as_text,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANALYTIC_DIMS = [k for k in DIMENSIONS if k != "overall"]

# --- runtime config: read from env on each call so /setup can change it live ---

def base_url() -> str:
    return os.environ.get("GRADER_BASE_URL", "http://127.0.0.1:8000/v1")


def api_key() -> str:
    return os.environ.get("GRADER_API_KEY", "")


def current_model() -> str:
    return os.environ.get("GRADER_MODEL", "deepseek-default")


def max_tokens() -> int:
    try:
        return int(os.environ.get("GRADER_MAX_TOKENS", "8000"))
    except ValueError:
        return 8000


def is_configured() -> bool:
    return bool(api_key())


# Backwards-compatible module attribute used in a few call sites / templates.
MODEL = current_model()

_client_cache: dict = {}
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Presets to make "bring your own backend" a one-click choice in /setup.
PROVIDER_PRESETS: dict[str, dict] = {
    "local_ollama": {
        "label": "本地 Ollama（完全免费/离线）",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
        "model": "qwen2.5:7b",
        "note": "先装 Ollama 并 `ollama pull qwen2.5:7b`。质量取决于本地模型。",
    },
    "lm_studio": {
        "label": "本地 LM Studio（完全免费/离线）",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "lm-studio",
        "model": "local-model",
        "note": "在 LM Studio 里启动本地服务器，模型名填你加载的那个。",
    },
    "zhipu": {
        "label": "智谱 GLM（自带 key，有免费额度档）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "",
        "model": "glm-4.6",
        "note": "到 open.bigmodel.cn 申请你自己的 key。",
    },
    "deepseek_official": {
        "label": "DeepSeek 官方（自带 key）",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "note": "到 platform.deepseek.com 申请你自己的 key。",
    },
    "custom": {
        "label": "自定义（任意 OpenAI 兼容端点）",
        "base_url": "",
        "api_key": "",
        "model": "",
        "note": "任何 OpenAI 兼容的 /v1 端点都行。",
    },
}


def apply_config(*, base_url: str, api_key: str, model: str, max_tokens: Optional[int] = None) -> None:
    """Update runtime config (env) and persist to .env, busting the client cache."""
    os.environ["GRADER_BASE_URL"] = base_url.strip()
    os.environ["GRADER_API_KEY"] = api_key.strip()
    os.environ["GRADER_MODEL"] = model.strip()
    if max_tokens:
        os.environ["GRADER_MAX_TOKENS"] = str(max_tokens)
    _client_cache.clear()
    _persist_env({
        "GRADER_BASE_URL": base_url.strip(),
        "GRADER_API_KEY": api_key.strip(),
        "GRADER_MODEL": model.strip(),
    })


def _persist_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in lines:
        m = re.match(r"\s*([A-Z_]+)\s*=", line)
        if m and m.group(1) in updates:
            key = m.group(1)
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(out) + "\n")


def _client() -> OpenAI:
    key, base = api_key(), base_url()
    if not key:
        raise RuntimeError("GRADER_API_KEY not configured")
    cached = _client_cache.get("c")
    if cached and _client_cache.get("k") == (key, base):
        return cached
    # max_retries=0: some proxies mute the key on bursty retries, so never auto-retry.
    client = OpenAI(base_url=base, api_key=key, timeout=180.0, max_retries=0)
    _client_cache["c"], _client_cache["k"] = client, (key, base)
    return client


@lru_cache(maxsize=1)
def _calibration() -> list[dict[str, Any]]:
    path = DATA_DIR / "calibration.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _calibration_block() -> str:
    anchors = _calibration()
    if not anchors:
        return ""
    out = ["CALIBRATION ANCHORS — real essays scored by trained human raters. "
           "Use these to anchor your scale; do not quote them in feedback.\n"]
    for i, a in enumerate(anchors, 1):
        sc = a["scores"]
        score_line = ", ".join(f"{DIMENSIONS[d]} {sc.get(d)}" for d in DIMENSIONS)
        out.append(f"[Anchor {i}] grade {a.get('grade')} — {score_line}")
        out.append(f"  EXCERPT: {a['text'][:600]}")
        out.append("")
    return "\n".join(out)


SYSTEM_PROMPT = """You are an experienced high-school writing teacher who has \
graded thousands of student essays. You are warm but honest: you name what works, \
you are specific about what doesn't, and every criticism comes with a concrete way \
to fix it. You never give vague praise ("good job") or vague criticism ("be clearer").

You score with the ELLIPSE English-proficiency rubric below. Scores are {smin}-{smax} \
in 0.5 steps.

{rubric}

{calibration}

GRADING METHOD — follow this order so your scores are evidence-based, not gut feeling:
1. For EACH analytic dimension, first find concrete evidence in the essay (quote-level), decide \
which band descriptor (1-5) it best matches, and write that as one short sentence in "rubric_check".
2. Only then assign the numeric score for that dimension — it must agree with the band you named.
3. Give the Overall score last: a holistic judgement that broadly reflects the analytic picture \
(not a strict average).

SCORING DISCIPLINE (counteract leniency):
- Most real student work lands at 2.5-4.0. Reserve 4.5-5 for genuinely polished writing and \
1-2 for work with pervasive breakdowns.
- Do NOT give every dimension the same score unless the evidence truly warrants it — a writer is \
usually stronger in some areas than others.
- A single recurring error type (e.g. subject-verb agreement) should pull Grammar down even if \
ideas are good; judge each dimension independently.

HOW TO ANNOTATE — like marking up a paper by hand:
- "quote" MUST be copied character-for-character from the essay (you will be checked against the \
source). Keep it SHORT — under 12 words — so it matches exactly. Do not paraphrase or fix typos in the quote.
- Tag each annotation with one type from: {types}.
- "comment" speaks to the student: short, specific, kind, actionable. "suggestion" gives a concrete \
rewrite (or "" if none).
- Mark strong moments too (type "praise") — students learn from what they did right.
- Produce 6 to 12 annotations spread across the WHOLE piece (beginning, middle, end), not clustered.
- Before finishing, re-read each "quote" and confirm it appears verbatim in the essay.

{fewshot}

{output_spec}"""


FEWSHOT = '''EXAMPLE (style only — shows the bar for specificity, not the scores to give):
Student text: "Their are many resson why school is important for kids in they life."
Good annotations:
  {"quote": "Their are many resson", "type": "conventions", "comment": "Two quick fixes here: 'Their' should be 'There' (existence), and 'resson' is misspelled.", "suggestion": "There are many reasons"}
  {"quote": "kids in they life", "type": "grammar", "comment": "Use the possessive 'their' before a noun, not 'they'.", "suggestion": "kids in their lives"}
Notice: each quote is short and verbatim; each comment names the exact problem and the fix.'''


def _output_spec() -> str:
    score_keys = ", ".join(f'"{d}"' for d in DIMENSIONS)
    check_keys = ", ".join(f'"{d}": "evidence + band level"' for d in DIMENSIONS)
    return (
        "OUTPUT FORMAT — reply with ONE JSON object and NOTHING else (no prose, no "
        "markdown fences, no <think>). Produce the keys in THIS ORDER (reason first, then score):\n\n"
        "{\n"
        f'  "rubric_check": {{ {check_keys} }},  // one short sentence per dimension, written BEFORE scoring\n'
        f'  "scores": {{ {score_keys} }},   // each a number 1-5 in 0.5 steps; must agree with rubric_check\n'
        '  "summary": "2-4 sentence holistic comment to the student",\n'
        '  "strengths": ["specific thing done well", "..."],\n'
        '  "priorities": ["highest-impact fix first", "..."],\n'
        '  "annotations": [\n'
        '    { "quote": "exact substring from the essay", "type": "one of the allowed types", '
        '"comment": "margin note to the student", "suggestion": "concrete rewrite or empty string" }\n'
        "  ]\n"
        "}\n\n"
        "Every score key is REQUIRED. annotations MUST be an array of 6-12 objects. "
        "Do not rename keys. Do not omit any key."
    )


def grade_essay(
    *,
    essay_text: str,
    assignment_prompt: Optional[str] = None,
    grade_level: Optional[str] = None,
    essay_type: str = "argumentative essay",
) -> dict[str, Any]:
    """Grade one essay. Returns the structured evaluation dict."""
    if not essay_text or not essay_text.strip():
        raise ValueError("essay_text is empty")

    context = [f"Essay type: {essay_type}."]
    if grade_level:
        context.append(f"Student grade level: {grade_level}.")
    if assignment_prompt:
        context.append(f"Assignment prompt:\n{assignment_prompt}")
    context.append(
        "Now evaluate the following student essay. Every quote in annotations must be an "
        "exact substring of the essay. Reply with the JSON object only.\n\n"
        f"--- STUDENT ESSAY ---\n{essay_text}\n--- END ESSAY ---"
    )

    system = SYSTEM_PROMPT.format(
        smin=SCALE_MIN, smax=SCALE_MAX,
        rubric=rubric_as_text(), calibration=_calibration_block(),
        types=", ".join(ANNOTATION_TYPES), fewshot=FEWSHOT, output_spec=_output_spec(),
    )

    try:
        resp = _client().chat.completions.create(
            model=current_model(),
            max_tokens=max_tokens(),
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(context)},
            ],
        )
    except Exception as exc:  # map provider errors to a clear, user-facing message
        raise RuntimeError(_friendly_error(exc)) from exc

    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise RuntimeError("Model returned an empty response")
    raw = _loads_loose(content)
    return _postprocess(raw, essay_text)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "mute" in low:
        m = re.search(r"mute_until=([0-9.]+)", msg)
        when = ""
        if m:
            import datetime as _dt
            ts = _dt.datetime.fromtimestamp(float(m.group(1)))
            when = f"（预计解禁：{ts:%Y-%m-%d %H:%M}）"
        return f"评分服务暂时限流：当前 key 被反代禁用{when}。稍后再试或更换 key。"
    if "rate" in low and "limit" in low:
        return "评分服务触发限流，请稍后再试。"
    if "connection" in low or "timeout" in low:
        return f"无法连接评分端点（{base_url()}）。确认本地服务/模型是否在运行。"
    return f"评分调用失败：{msg}"


def _loads_loose(s: str) -> dict[str, Any]:
    s = s.strip()
    # drop reasoning blocks some models prepend
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # strip ```json fences if present
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.MULTILINE).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # last resort: grab the outermost {...}
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise RuntimeError("Could not parse evaluation JSON from model output")


def _postprocess(result: dict[str, Any], essay_text: str) -> dict[str, Any]:
    """Fill gaps, clamp scores, verify quotes resolve, attach char offsets."""
    result.setdefault("scores", {})
    result.setdefault("summary", "")
    result.setdefault("strengths", [])
    result.setdefault("priorities", [])
    result.setdefault("annotations", [])
    rc = result.get("rubric_check")
    result["rubric_check"] = rc if isinstance(rc, dict) else {}

    scores = result["scores"] if isinstance(result["scores"], dict) else {}
    analytic_vals = []
    for d in ANALYTIC_DIMS:
        v = _clamp_score(scores.get(d))
        scores[d] = v
        if v is not None:
            analytic_vals.append(v)
    overall = _clamp_score(scores.get("overall"))
    if overall is None:  # derive from analytic mean if the model skipped it
        overall = round((sum(analytic_vals) / len(analytic_vals)) * 2) / 2 if analytic_vals else SCALE_MIN
    scores["overall"] = overall
    # default any still-missing analytic dim to the overall
    for d in ANALYTIC_DIMS:
        if scores[d] is None:
            scores[d] = overall
    result["scores"] = scores

    anns = []
    for a in result["annotations"]:
        if not isinstance(a, dict):
            continue
        quote = (a.get("quote") or "").strip()
        a["quote"] = quote
        a["type"] = a.get("type") if a.get("type") in ANNOTATION_TYPES else "style"
        a["comment"] = a.get("comment") or ""
        a["suggestion"] = a.get("suggestion") or ""
        start = essay_text.find(quote) if quote else -1
        if start < 0 and quote:  # tolerate minor whitespace/case differences
            start = _fuzzy_find(essay_text, quote)
        a["start"] = start
        a["end"] = start + len(quote) if start >= 0 else -1
        a["located"] = start >= 0
        anns.append(a)
    anns.sort(key=lambda x: (x["start"] if x["start"] >= 0 else 1 << 30))
    result["annotations"] = anns
    result["strengths"] = [s for s in result["strengths"] if isinstance(s, str) and s.strip()]
    result["priorities"] = [p for p in result["priorities"] if isinstance(p, str) and p.strip()]
    return result


def _clamp_score(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    f = max(SCALE_MIN, min(SCALE_MAX, round(f * 2) / 2))
    return f


def _fuzzy_find(text: str, quote: str) -> int:
    """Locate a quote allowing collapsed whitespace; returns char offset or -1."""
    norm_q = re.sub(r"\s+", " ", quote).strip()
    pattern = re.escape(norm_q).replace(r"\ ", r"\s+")
    m = re.search(pattern, text)
    return m.start() if m else -1
