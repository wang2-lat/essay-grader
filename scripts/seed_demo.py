"""Seed a demo teacher, student, and assignment so you can try the app fast.

Login after running:
    teacher  ->  user: teacher  pass: demo1234
    student  ->  user: student  pass: demo1234

Usage: ./.venv/bin/python scripts/seed_demo.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from passlib.context import CryptContext  # noqa: E402
from sqlmodel import select  # noqa: E402

from app.db import Assignment, User, get_session, init_db  # noqa: E402

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def ensure_user(s, username, name, role) -> User:
    u = s.exec(select(User).where(User.username == username)).first()
    if u:
        return u
    u = User(username=username, display_name=name, role=role,
             password_hash=pwd.hash("demo1234"))
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def main() -> None:
    init_db()
    with get_session() as s:
        teacher = ensure_user(s, "teacher", "演示老师", "teacher")
        ensure_user(s, "student", "演示学生", "student")
        has = s.exec(select(Assignment).where(Assignment.teacher_id == teacher.id)).first()
        if not has:
            s.add(Assignment(
                teacher_id=teacher.id,
                title="议论文 · 手机是否应在校园被禁",
                prompt="Should mobile phones be banned in schools? Take a clear position and support it with reasons and examples.",
                essay_type="argumentative essay",
                grade_level="Grade 10",
            ))
            s.commit()
    print("Seeded. Login: teacher/demo1234 or student/demo1234")


if __name__ == "__main__":
    main()
