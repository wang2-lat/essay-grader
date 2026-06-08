"""FastAPI app: auth, teacher/student flows, and the grading endpoint."""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env BEFORE importing grader — grader reads its config at module import.
load_dotenv()

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from .core import grader
from .core import limiter
from .core.render import annotated_html
from .ap import rubric as ap_rubric
from .ap import scorer as ap_scorer
from .db import (
    Assignment,
    Evaluation,
    Submission,
    User,
    get_session,
    init_db,
)

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Essay Grader")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", secrets.token_hex(32)),
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# CORS for the browser extension. Auth is via the X-API-Key header (no cookies),
# so a wildcard origin is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

API_TOKEN = os.environ.get("GRADER_API_TOKEN", "")


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ----------------------------- auth helpers -----------------------------

def current_user(request: Request) -> Optional[User]:
    uid = request.session.get("uid")
    if not uid:
        return None
    with get_session() as s:
        return s.get(User, uid)


def require(request: Request, role: Optional[str] = None) -> User:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    if role and user.role != role:
        raise HTTPException(status_code=403, detail="Wrong role for this page")
    return user


@app.exception_handler(HTTPException)
async def _redirect_unauth(request: Request, exc: HTTPException):
    if exc.status_code == 302 and "Location" in (exc.headers or {}):
        return RedirectResponse(exc.headers["Location"], status_code=302)
    return HTMLResponse(f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)


# ----------------------------- auth routes -----------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/dashboard" if current_user(request) else "/login")


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
):
    if role not in ("teacher", "student"):
        role = "student"
    with get_session() as s:
        exists = s.exec(select(User).where(User.username == username)).first()
        if exists:
            return templates.TemplateResponse(
                "register.html", {"request": request, "error": "用户名已被占用"}, status_code=400
            )
        user = User(
            username=username.strip(),
            password_hash=pwd.hash(password),
            role=role,
            display_name=display_name.strip() or username,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        request.session["uid"] = user.id
        request.session["role"] = user.role
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with get_session() as s:
        user = s.exec(select(User).where(User.username == username)).first()
        if not user or not pwd.verify(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "用户名或密码错误"}, status_code=401
            )
        request.session["uid"] = user.id
        request.session["role"] = user.role
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ----------------------------- dashboard -----------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require(request)
    with get_session() as s:
        if user.role == "teacher":
            assignments = s.exec(
                select(Assignment).where(Assignment.teacher_id == user.id).order_by(Assignment.created_at.desc())
            ).all()
            subs = s.exec(select(Submission).order_by(Submission.created_at.desc())).all()
            a_ids = {a.id for a in assignments}
            subs = [x for x in subs if x.assignment_id in a_ids][:20]
            return templates.TemplateResponse(
                "dashboard_teacher.html",
                {"request": request, "user": user, "assignments": assignments, "subs": subs},
            )
        # student
        assignments = s.exec(select(Assignment).order_by(Assignment.created_at.desc())).all()
        my_subs = s.exec(
            select(Submission).where(Submission.student_id == user.id).order_by(Submission.created_at.desc())
        ).all()
        return templates.TemplateResponse(
            "dashboard_student.html",
            {"request": request, "user": user, "assignments": assignments, "subs": my_subs},
        )


# ----------------------------- teacher: assignments -----------------------------

@app.get("/assignments/new", response_class=HTMLResponse)
def assignment_new(request: Request):
    require(request, "teacher")
    return templates.TemplateResponse("assignment_new.html", {"request": request})


@app.post("/assignments")
def assignment_create(
    request: Request,
    title: str = Form(...),
    prompt: str = Form(""),
    essay_type: str = Form("argumentative essay"),
    grade_level: str = Form(""),
):
    user = require(request, "teacher")
    with get_session() as s:
        a = Assignment(
            teacher_id=user.id, title=title.strip(), prompt=prompt.strip(),
            essay_type=essay_type, grade_level=grade_level.strip(),
        )
        s.add(a)
        s.commit()
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/assignments/{aid}", response_class=HTMLResponse)
def assignment_detail(request: Request, aid: int):
    user = require(request, "teacher")
    with get_session() as s:
        a = s.get(Assignment, aid)
        if not a or a.teacher_id != user.id:
            raise HTTPException(404, "Assignment not found")
        subs = s.exec(
            select(Submission).where(Submission.assignment_id == aid).order_by(Submission.created_at.desc())
        ).all()
        rows = []
        for sub in subs:
            ev = s.exec(select(Evaluation).where(Evaluation.submission_id == sub.id)).first()
            student = s.get(User, sub.student_id)
            rows.append({"sub": sub, "ev": ev, "student": student})
    return templates.TemplateResponse(
        "assignment_detail.html", {"request": request, "user": user, "a": a, "rows": rows}
    )


# ----------------------------- student: submit + grade -----------------------------

@app.get("/submit", response_class=HTMLResponse)
def submit_form(request: Request, assignment_id: Optional[int] = None):
    user = require(request, "student")
    with get_session() as s:
        assignments = s.exec(select(Assignment).order_by(Assignment.created_at.desc())).all()
        selected = s.get(Assignment, assignment_id) if assignment_id else None
    return templates.TemplateResponse(
        "submit.html",
        {"request": request, "user": user, "assignments": assignments, "selected": selected},
    )


@app.post("/submit")
def submit_essay(
    request: Request,
    essay_text: str = Form(...),
    title: str = Form(""),
    assignment_id: str = Form(""),
):
    user = require(request, "student")
    aid = int(assignment_id) if assignment_id.strip().isdigit() else None

    with get_session() as s:
        assignment = s.get(Assignment, aid) if aid else None
        prompt = assignment.prompt if assignment else None
        etype = assignment.essay_type if assignment else "essay"
        glevel = assignment.grade_level if assignment else ""

        sub = Submission(
            assignment_id=aid, student_id=user.id,
            title=title.strip() or (assignment.title if assignment else "Untitled"),
            essay_text=essay_text,
        )
        s.add(sub)
        s.commit()
        s.refresh(sub)
        sub_id = sub.id

        try:
            result = grader.grade_essay(
                essay_text=essay_text, assignment_prompt=prompt,
                grade_level=glevel, essay_type=etype,
            )
            ev = Evaluation(
                submission_id=sub_id, model=grader.current_model(),
                scores=result["scores"], summary=result["summary"],
                strengths=result["strengths"], priorities=result["priorities"],
                annotations=result["annotations"],
            )
            s.add(ev)
            sub.status = "graded"
            s.add(sub)
            s.commit()
        except Exception as exc:  # surface grading failure, keep submission
            sub.status = "error"
            s.add(sub)
            s.commit()
            raise HTTPException(500, f"评分失败: {exc}")

    return RedirectResponse(f"/submissions/{sub_id}", status_code=302)


# ----------------------------- result view -----------------------------

@app.get("/submissions/{sid}", response_class=HTMLResponse)
def submission_detail(request: Request, sid: int):
    user = require(request)
    with get_session() as s:
        sub = s.get(Submission, sid)
        if not sub:
            raise HTTPException(404, "Submission not found")
        # access control: owner student, or teacher of the assignment
        allowed = sub.student_id == user.id
        assignment = s.get(Assignment, sub.assignment_id) if sub.assignment_id else None
        if user.role == "teacher" and assignment and assignment.teacher_id == user.id:
            allowed = True
        if not allowed:
            raise HTTPException(403, "你无权查看这份作文")
        ev = s.exec(select(Evaluation).where(Evaluation.submission_id == sid)).first()
        student = s.get(User, sub.student_id)

    annotations = []
    body_html = sub.essay_text
    if ev:
        annotations = [dict(a, _idx=i) for i, a in enumerate(ev.annotations)]
        body_html = annotated_html(sub.essay_text, annotations)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request, "user": user, "sub": sub, "ev": ev,
            "assignment": assignment, "student": student,
            "annotations": annotations, "body_html": body_html,
            "dims": grader.DIMENSIONS, "is_teacher": user.role == "teacher",
        },
    )


@app.post("/submissions/{sid}/teacher-note")
def teacher_note(request: Request, sid: int, note: str = Form("")):
    user = require(request, "teacher")
    with get_session() as s:
        sub = s.get(Submission, sid)
        if not sub:
            raise HTTPException(404, "Submission not found")
        assignment = s.get(Assignment, sub.assignment_id) if sub.assignment_id else None
        if not assignment or assignment.teacher_id != user.id:
            raise HTTPException(403, "无权批注")
        ev = s.exec(select(Evaluation).where(Evaluation.submission_id == sid)).first()
        if ev:
            ev.teacher_note = note.strip()
            s.add(ev)
            s.commit()
    return RedirectResponse(f"/submissions/{sid}", status_code=302)


# ----------------------------- public JSON API (for the browser extension) -----------------------------

class GradeRequest(BaseModel):
    text: str
    prompt: Optional[str] = None
    grade_level: Optional[str] = None
    essay_type: str = "argumentative essay"


class APGradeRequest(BaseModel):
    text: str
    frq_type: str = "argument"  # synthesis | rhetorical_analysis | argument
    prompt: Optional[str] = None
    source_material: Optional[str] = None
    passes: int = 1


@app.get("/api/health")
def api_health():
    return {"ok": True, "model": grader.current_model(), "configured": grader.is_configured()}


# ----------------------------- first-run setup (bring your own backend) -----------------------------

@app.get("/setup", response_class=HTMLResponse)
def setup_form(request: Request, saved: int = 0):
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "presets": grader.PROVIDER_PRESETS,
            "current": {
                "base_url": grader.base_url(),
                "model": grader.current_model(),
                "has_key": grader.is_configured(),
            },
            "saved": bool(saved),
        },
    )


@app.post("/setup")
def setup_save(
    request: Request,
    base_url: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(...),
):
    # keep the existing key if the field is left blank (so we don't wipe it)
    key = api_key.strip() or grader.api_key()
    grader.apply_config(base_url=base_url, api_key=key, model=model)
    return RedirectResponse("/setup?saved=1", status_code=302)


@app.get("/setup/test")
def setup_test():
    """Cheap real connectivity test against the configured model."""
    if not grader.is_configured():
        return JSONResponse({"ok": False, "error": "尚未配置 API key"}, status_code=400)
    try:
        grader._client().chat.completions.create(
            model=grader.current_model(),
            max_tokens=5,
            messages=[{"role": "user", "content": "Reply with: OK"}],
        )
        return {"ok": True, "model": grader.current_model()}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": grader._friendly_error(exc)}, status_code=502)


@app.post("/api/grade")
def api_grade(body: GradeRequest, x_api_key: str = Header(default="")):
    if API_TOKEN and x_api_key != API_TOKEN:
        return JSONResponse({"error": "invalid api key"}, status_code=401)
    if not body.text.strip():
        return JSONResponse({"error": "empty text"}, status_code=400)
    blocked = limiter.check(len(body.text))
    if blocked:
        return JSONResponse({"error": blocked}, status_code=429)
    try:
        result = grader.grade_essay(
            essay_text=body.text,
            assignment_prompt=body.prompt,
            grade_level=body.grade_level,
            essay_type=body.essay_type,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
    # echo the text so the client can map char offsets back onto its own selection
    result["text"] = body.text
    return result


@app.post("/api/ap_grade")
def api_ap_grade(body: APGradeRequest, x_api_key: str = Header(default="")):
    """Score an essay on the official AP English Language 6-point analytic rubric."""
    if API_TOKEN and x_api_key != API_TOKEN:
        return JSONResponse({"error": "invalid api key"}, status_code=401)
    if not body.text.strip():
        return JSONResponse({"error": "empty text"}, status_code=400)
    if body.frq_type not in ap_rubric.FRQ_TYPES:
        return JSONResponse(
            {"error": f"frq_type must be one of {list(ap_rubric.FRQ_TYPES)}"},
            status_code=400,
        )
    blocked = limiter.check(len(body.text))
    if blocked:
        return JSONResponse({"error": blocked}, status_code=429)
    try:
        result = ap_scorer.score_essay(
            body.text,
            body.frq_type,
            prompt_text=body.prompt,
            source_material=body.source_material,
            passes=max(1, min(body.passes, 5)),
        )
    except Exception as exc:
        return JSONResponse({"error": grader._friendly_error(exc)}, status_code=502)
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "scoring failed")},
                            status_code=502)
    result["text"] = body.text
    return result
