"""Database models and session helpers (SQLite via SQLModel)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, Session, SQLModel, create_engine

DB_PATH = Path(__file__).resolve().parent.parent / "essaygrader.db"
ENGINE = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    role: str  # "teacher" | "student"
    display_name: str
    created_at: dt.datetime = Field(default_factory=_now)


class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: int = Field(index=True, foreign_key="user.id")
    title: str
    prompt: str = Field(sa_column=Column(Text))
    essay_type: str = "argumentative essay"
    grade_level: str = ""
    created_at: dt.datetime = Field(default_factory=_now)


class Submission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: Optional[int] = Field(default=None, foreign_key="assignment.id", index=True)
    student_id: int = Field(index=True, foreign_key="user.id")
    title: str = ""
    essay_text: str = Field(sa_column=Column(Text))
    status: str = "graded"  # "graded" | "error"
    created_at: dt.datetime = Field(default_factory=_now)


class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    submission_id: int = Field(index=True, foreign_key="submission.id")
    model: str = ""
    scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    summary: str = Field(default="", sa_column=Column(Text))
    strengths: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    priorities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    annotations: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    teacher_note: str = Field(default="", sa_column=Column(Text))  # optional teacher override/comment
    teacher_scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: dt.datetime = Field(default_factory=_now)


def init_db() -> None:
    SQLModel.metadata.create_all(ENGINE)


def get_session() -> Session:
    return Session(ENGINE)
