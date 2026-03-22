"""Consolidated /student/me (and /students/me) payload for logged-in students."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Student, User
from services.analytics import build_student_dashboard, resolve_risk_level

logger = logging.getLogger(__name__)


def _summary_for_student(db: Session, student_id: int) -> dict:
    from models.entities import SemesterResult

    result = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student_id)
        .order_by(SemesterResult.semester.desc())
        .first()
    )
    total = db.query(Attendance).filter(Attendance.student_id == student_id).count()
    present = (
        db.query(Attendance)
        .filter(Attendance.student_id == student_id, Attendance.status == AttendanceStatus.PRESENT)
        .count()
    )
    attendance_pct = round((present * 100.0 / total), 2) if total else 0
    return {
        "student_id": student_id,
        "attendance_pct": attendance_pct,
        "sgpa": float(result.sgpa) if result else 0,
        "cgpa": float(result.cgpa) if result else 0,
        "backlogs": int(result.backlogs) if result else 0,
    }


def _merge_subjects(dashboard: dict) -> list[dict]:
    marks_rows = dashboard.get("marks") or []
    att_rows = dashboard.get("attendance") or []
    by_name: dict[str, dict] = {}
    for m in marks_rows:
        name = m.get("subject_name") or m.get("subject") or ""
        if not name:
            continue
        by_name[name] = {
            "name": name,
            "marks": float(m["marks"]) if m.get("marks") is not None else None,
            "attendance": None,
        }
    for a in att_rows:
        name = a.get("subject") or ""
        if not name:
            continue
        pct = a.get("attendance_pct")
        if name in by_name:
            by_name[name]["attendance"] = pct
        else:
            by_name[name] = {"name": name, "marks": None, "attendance": pct}
    return [by_name[k] for k in sorted(by_name.keys())]


def _average_marks(dashboard: dict) -> float | None:
    marks_rows = dashboard.get("marks") or []
    if not marks_rows:
        return None
    values = [float(m["marks"]) for m in marks_rows if m.get("marks") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_student_me_response(db: Session, current_user: User) -> dict | None:
    """
    Full student profile + summary + dashboard + merged subjects for the UI.
    Only data for current_user's linked Student row.
    """
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        logger.warning("student/me: no Student row for user_id=%s email=%s", current_user.id, current_user.email)
        return None

    logger.info("student/me: user_id=%s student_id=%s", current_user.id, student.id)

    dashboard = build_student_dashboard(db, student.id)
    summary = _summary_for_student(db, student.id)
    subjects = _merge_subjects(dashboard)
    avg_marks = _average_marks(dashboard)
    risk_score = (dashboard.get("risk") or {}).get("risk_score")
    risk_code = resolve_risk_level(risk_score)
    risk_label = risk_code.title() if risk_code else "Unknown"

    return {
        "id": student.id,
        "name": current_user.name,
        "email": current_user.email,
        "roll_number": student.roll_number,
        "department": student.department,
        "year": student.year,
        "section": student.section,
        "subjects": subjects,
        "attendance_overall": summary["attendance_pct"],
        "average_marks": avg_marks,
        "risk": risk_label,
        "summary": summary,
        "dashboard": dashboard,
    }
