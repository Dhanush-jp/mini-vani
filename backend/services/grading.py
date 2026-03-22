from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Grade, RiskAnalysis, SemesterResult

GRADE_POINTS = {
    "A+": 10.0,
    "A": 9.0,
    "B+": 8.0,
    "B": 7.0,
    "C": 6.0,
    "D": 5.0,
    "F": 0.0,
}


def compute_grade(marks: float) -> tuple[str, bool]:
    if marks >= 90:
        return "A+", True
    if marks >= 80:
        return "A", True
    if marks >= 70:
        return "B+", True
    if marks >= 60:
        return "B", True
    if marks >= 50:
        return "C", True
    if marks >= 40:
        return "D", True
    return "F", False


def recompute_student_metrics(db: Session, student_id: int) -> None:
    semester_rows = db.query(Grade.semester).filter(Grade.student_id == student_id).distinct().all()
    semester_numbers = sorted(row.semester for row in semester_rows)

    semester_snapshots: list[tuple[int, float, int]] = []
    for semester in semester_numbers:
        grades = db.query(Grade).filter(Grade.student_id == student_id, Grade.semester == semester).all()
        if not grades:
            continue
        sgpa = round(sum(GRADE_POINTS.get(grade.grade, 0.0) for grade in grades) / len(grades), 2)
        backlogs = sum(1 for grade in grades if not grade.is_pass)
        semester_snapshots.append((semester, sgpa, backlogs))

    cumulative: list[float] = []
    for semester, sgpa, backlogs in semester_snapshots:
        cumulative.append(sgpa)
        cgpa = round(sum(cumulative) / len(cumulative), 2)
        row = db.query(SemesterResult).filter(SemesterResult.student_id == student_id, SemesterResult.semester == semester).first()
        if row:
            row.sgpa = sgpa
            row.cgpa = cgpa
            row.backlogs = backlogs
        else:
            db.add(SemesterResult(student_id=student_id, semester=semester, sgpa=sgpa, cgpa=cgpa, backlogs=backlogs))

    attendance_row = (
        db.query(
            func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
            func.count(Attendance.id).label("total"),
        )
        .filter(Attendance.student_id == student_id)
        .first()
    )
    latest_result = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student_id)
        .order_by(SemesterResult.semester.desc())
        .first()
    )
    present = float(attendance_row.present or Decimal("0")) if attendance_row else 0.0
    total = int(attendance_row.total or 0) if attendance_row else 0
    attendance_pct = round((present * 100.0 / total), 2) if total else 0
    cgpa = float(latest_result.cgpa) if latest_result else 0
    backlogs = int(latest_result.backlogs) if latest_result else 0

    risk_score = round(min(10.0, max(0.0, ((100 - attendance_pct) / 20.0) + max(0.0, 7.5 - cgpa) + (backlogs * 0.8))), 2)
    suggestions = []
    if attendance_pct < 75:
        suggestions.append("Improve attendance consistency.")
    if cgpa < 6.5:
        suggestions.append("Schedule remedial academic support.")
    if backlogs > 0:
        suggestions.append("Prioritize failed subjects in the next review cycle.")
    if not suggestions:
        suggestions.append("Maintain current performance and attendance discipline.")

    risk_row = db.query(RiskAnalysis).filter(RiskAnalysis.student_id == student_id).first()
    if risk_row:
        risk_row.risk_score = risk_score
        risk_row.suggestions = " ".join(suggestions)
    else:
        db.add(RiskAnalysis(student_id=student_id, risk_score=risk_score, suggestions=" ".join(suggestions)))
