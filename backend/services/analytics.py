from collections.abc import Iterable

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Grade, RiskAnalysis, SemesterResult, Student, Subject, TeacherStudent, User, UserRole
from schemas.common import StudentFilter
from services.access import get_teacher_or_404


def _teacher_student_ids(db: Session, user: User) -> list[int]:
    teacher = get_teacher_or_404(db, user.id)
    return [row.student_id for row in db.query(TeacherStudent.student_id).filter(TeacherStudent.teacher_id == teacher.id).all()]


def allowed_student_scope(db: Session, user: User):
    if user.role == UserRole.ADMIN:
        return db.query(Student.id)
    if user.role == UserRole.STUDENT:
        return db.query(Student.id).filter(Student.user_id == user.id)
    ids = _teacher_student_ids(db, user)
    if not ids:
        return db.query(Student.id).filter(Student.id == -1)
    return db.query(Student.id).filter(Student.id.in_(ids))


def resolve_risk_level(risk_score: float | None) -> str | None:
    if risk_score is None:
        return None
    if risk_score < 4:
        return "LOW"
    if risk_score <= 7:
        return "MEDIUM"
    return "HIGH"


def apply_student_filters(db: Session, user: User, filters: StudentFilter) -> Iterable[int]:
    base = allowed_student_scope(db, user).subquery()
    query = db.query(Student.id).join(base, Student.id == base.c.id)

    if filters.semester is not None:
        query = query.join(
            SemesterResult,
            and_(SemesterResult.student_id == Student.id, SemesterResult.semester == filters.semester),
        )

    if filters.cgpa_min is not None:
        query = query.join(SemesterResult, SemesterResult.student_id == Student.id).filter(SemesterResult.cgpa >= filters.cgpa_min)
    if filters.cgpa_max is not None:
        query = query.join(SemesterResult, SemesterResult.student_id == Student.id).filter(SemesterResult.cgpa <= filters.cgpa_max)
    if filters.is_pass is not None:
        query = query.join(Grade, Grade.student_id == Student.id).filter(Grade.is_pass == filters.is_pass)
    if filters.subject_id is not None:
        query = query.join(Grade, Grade.student_id == Student.id).filter(Grade.subject_id == filters.subject_id)
    if filters.risk_level is not None:
        query = query.join(RiskAnalysis, RiskAnalysis.student_id == Student.id)
        if filters.risk_level == "LOW":
            query = query.filter(RiskAnalysis.risk_score < 4)
        elif filters.risk_level == "MEDIUM":
            query = query.filter(RiskAnalysis.risk_score.between(4, 7))
        else:
            query = query.filter(RiskAnalysis.risk_score > 7)
    if filters.student_id is not None:
        query = query.filter(Student.id == filters.student_id)
    if filters.department is not None:
        query = query.filter(Student.department == filters.department)
    if filters.year is not None:
        query = query.filter(Student.year == filters.year)
    if filters.section is not None:
        query = query.filter(Student.section == filters.section)
    if filters.search is not None:
        needle = f"%{filters.search.strip()}%"
        query = query.join(User, User.id == Student.user_id).filter(
            (User.name.ilike(needle)) | (User.email.ilike(needle)) | (Student.roll_number.ilike(needle))
        )

    rows = query.distinct().all()
    ids = [row.id for row in rows]
    if filters.attendance_min is not None or filters.attendance_max is not None:
        att_q = (
            db.query(
                Attendance.student_id.label("student_id"),
                (func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)) * 100.0 / func.count(Attendance.id)).label(
                    "attendance_pct"
                ),
            )
            .filter(Attendance.student_id.in_(ids))
            .group_by(Attendance.student_id)
        )
        min_v = filters.attendance_min if filters.attendance_min is not None else 0
        max_v = filters.attendance_max if filters.attendance_max is not None else 100
        rows = att_q.having(func.round(func.sum(case((Attendance.status == "PRESENT", 1), else_=0)) * 100.0 / func.count(Attendance.id), 2).between(min_v, max_v)).all()
        ids = [r.student_id for r in rows]
    return ids


def build_student_dashboard(db: Session, student_id: int) -> dict:
    semester_rows = (
        db.query(SemesterResult.semester, SemesterResult.sgpa, SemesterResult.cgpa, SemesterResult.backlogs)
        .filter(SemesterResult.student_id == student_id)
        .order_by(SemesterResult.semester.asc())
        .all()
    )
    marks_rows = (
        db.query(
            Grade.id.label("grade_id"),
            Subject.id.label("subject_id"),
            Subject.name.label("subject_name"),
            Subject.code.label("subject_code"),
            Grade.semester.label("semester"),
            Grade.marks.label("marks"),
            Grade.grade.label("grade"),
            Grade.is_pass.label("is_pass"),
        )
        .join(Subject, Subject.id == Grade.subject_id)
        .filter(Grade.student_id == student_id)
        .all()
    )
    attendance_rows = (
        db.query(
            Subject.name,
            func.count(Attendance.id).label("total"),
            func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
        )
        .join(Subject, Subject.id == Attendance.subject_id)
        .filter(Attendance.student_id == student_id)
        .group_by(Subject.name)
        .all()
    )
    risk = db.query(RiskAnalysis).filter(RiskAnalysis.student_id == student_id).first()

    return {
        "trends": [{"semester": s.semester, "sgpa": s.sgpa, "cgpa": s.cgpa} for s in semester_rows],
        "backlogs": [{"semester": s.semester, "backlogs": s.backlogs} for s in semester_rows],
        "marks": [
            {
                "id": m.grade_id,
                "student_id": student_id,
                "subject_id": m.subject_id,
                "subject_name": m.subject_name,
                "subject_code": m.subject_code,
                "semester": m.semester,
                "marks": float(m.marks),
                "grade": m.grade,
                "is_pass": m.is_pass,
                "subject": m.subject_name,
            }
            for m in marks_rows
        ],
        "attendance": [
            {"subject": a.name, "attendance_pct": round((a.present or 0) * 100.0 / a.total, 2) if a.total else 0} for a in attendance_rows
        ],
        "pass_fail_ratio": {
            "pass": sum(1 for m in marks_rows if m.is_pass),
            "fail": sum(1 for m in marks_rows if not m.is_pass),
        },
        "risk": {
            "risk_score": risk.risk_score if risk else None,
            "suggestions": risk.suggestions if risk else None,
            "prediction_date": risk.prediction_date if risk else None,
        },
    }
