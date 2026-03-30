from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Export, ExportType, Grade, RiskAnalysis, SemesterResult, Student, Subject, User
from schemas.common import StudentFilter
from services.access import assert_student_access
from services.analytics import apply_student_filters
from services.excel_export import workbook_bytes_from_rows


def _build_students_export_rows(db: Session, student_ids: list[int]) -> list[dict]:
    if not student_ids:
        return []

    latest_results = (
        db.query(
            SemesterResult.student_id,
            func.max(SemesterResult.semester).label("latest_sem"),
        )
        .filter(SemesterResult.student_id.in_(student_ids))
        .group_by(SemesterResult.student_id)
        .subquery()
    )
    sem_rows = (
        db.query(SemesterResult.student_id, SemesterResult.sgpa, SemesterResult.cgpa, SemesterResult.backlogs)
        .join(
            latest_results,
            (latest_results.c.student_id == SemesterResult.student_id)
            & (latest_results.c.latest_sem == SemesterResult.semester),
        )
        .all()
    )
    sem_map = {r.student_id: r for r in sem_rows}
    att_rows = (
        db.query(
            Attendance.student_id,
            (func.sum(case((Attendance.status == "PRESENT", 1), else_=0)) * 100.0 / func.count(Attendance.id)).label(
                "attendance_pct"
            ),
        )
        .filter(Attendance.student_id.in_(student_ids))
        .group_by(Attendance.student_id)
        .all()
    )
    att_map = {r.student_id: round(float(r.attendance_pct), 2) for r in att_rows if r.attendance_pct is not None}
    risks = db.query(RiskAnalysis).filter(RiskAnalysis.student_id.in_(student_ids)).all()
    risk_map = {r.student_id: float(r.risk_score) for r in risks}

    rows = (
        db.query(Student, User.name, User.email)
        .join(User, User.id == Student.user_id)
        .filter(Student.id.in_(student_ids))
        .all()
    )
    result: list[dict] = []
    for student, name, email in rows:
        sem = sem_map.get(student.id)
        result.append(
            {
                "Name": name,
                "Email": email,
                "Department": student.department,
                "CGPA": float(sem.cgpa) if sem else None,
                "SGPA": float(sem.sgpa) if sem else None,
                "Attendance %": att_map.get(student.id),
                "Backlogs": int(sem.backlogs) if sem else None,
                "Risk Score": risk_map.get(student.id),
            }
        )
    return result


def export_students(db: Session, current_user: User, filters: StudentFilter) -> bytes:
    student_ids = list(apply_student_filters(db, current_user, filters))
    export_rows = _build_students_export_rows(db, student_ids)
    content = workbook_bytes_from_rows(export_rows, "Students")
    try:
        db.add(Export(user_id=current_user.id, type=ExportType.STUDENTS, filters=filters.model_dump()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return content


def export_single_student(db: Session, current_user: User, student_id: int, filters: StudentFilter) -> bytes:
    assert_student_access(db, current_user, student_id)
    query = (
        db.query(
            Subject.name.label("Subject"),
            Grade.marks.label("Marks"),
            Grade.grade.label("Grade"),
            Grade.is_pass.label("Pass/Fail"),
            (func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)) * 100.0 / func.count(Attendance.id)).label(
                "Attendance %"
            ),
            SemesterResult.sgpa.label("SGPA"),
            SemesterResult.cgpa.label("CGPA"),
            RiskAnalysis.risk_score.label("Risk Score"),
        )
        .join(Subject, Subject.id == Grade.subject_id)
        .outerjoin(Attendance, (Attendance.student_id == Grade.student_id) & (Attendance.subject_id == Grade.subject_id))
        .outerjoin(
            SemesterResult,
            (SemesterResult.student_id == Grade.student_id) & (SemesterResult.semester == Grade.semester),
        )
        .outerjoin(RiskAnalysis, RiskAnalysis.student_id == Grade.student_id)
        .filter(Grade.student_id == student_id)
        .group_by(Subject.name, Grade.marks, Grade.grade, Grade.is_pass, SemesterResult.sgpa, SemesterResult.cgpa, RiskAnalysis.risk_score)
    )
    if filters.semester is not None:
        query = query.filter(Grade.semester == filters.semester)
    if filters.subject_id is not None:
        query = query.filter(Grade.subject_id == filters.subject_id)
    if filters.is_pass is not None:
        query = query.filter(Grade.is_pass == filters.is_pass)
    rows = query.all()
    export_rows: list[dict] = []
    for r in rows:
        m = r._mapping
        export_rows.append(
            {
                "Subject": m["Subject"],
                "Marks": float(m["Marks"]) if m["Marks"] is not None else None,
                "Grade": m["Grade"],
                "Pass/Fail": "Pass" if m["Pass/Fail"] else "Fail",
                "Attendance %": round(float(m["Attendance %"]), 2) if m["Attendance %"] is not None else None,
                "SGPA": float(m["SGPA"]) if m["SGPA"] is not None else None,
                "CGPA": float(m["CGPA"]) if m["CGPA"] is not None else None,
                "Risk Score": float(m["Risk Score"]) if m["Risk Score"] is not None else None,
            }
        )
    content = workbook_bytes_from_rows(export_rows, "Student")
    try:
        db.add(
            Export(
                user_id=current_user.id,
                type=ExportType.SINGLE_STUDENT,
                filters={**filters.model_dump(), "student_id": student_id},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return content
