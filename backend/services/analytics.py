from collections.abc import Iterable

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Grade, RiskAnalysis, SemesterResult, Student, Subject, TeacherStudent, User, UserRole
from schemas.common import StudentFilter
from services.access import get_teacher_or_404
from services.helpers import safe_percentage, safe_float


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
    from models.entities import AcademicRecord, Subject
    
    semester_rows = (
        db.query(SemesterResult.semester, SemesterResult.sgpa, SemesterResult.cgpa, SemesterResult.backlogs)
        .filter(SemesterResult.student_id == student_id)
        .order_by(SemesterResult.semester.asc())
        .all()
    )

    # Use AcademicRecord (source of truth for imported data)
    academic_rows = (
        db.query(
            AcademicRecord,
            Subject.name.label("subject_name"),
            Subject.code.label("subject_code")
        )
        .join(Subject, Subject.id == AcademicRecord.subject_id)
        .filter(AcademicRecord.student_id == student_id)
        .all()
    )

    risk = db.query(RiskAnalysis).filter(RiskAnalysis.student_id == student_id).first()

    return {
        "trends": [{"semester": s.semester, "sgpa": s.sgpa, "cgpa": s.cgpa} for s in semester_rows],
        "backlogs": [{"semester": s.semester, "backlogs": s.backlogs} for s in semester_rows],
        "marks": [
            {
                "id": row.AcademicRecord.id,
                "student_id": student_id,
                "subject_id": row.AcademicRecord.subject_id,
                "subject_name": row.subject_name,
                "subject_code": row.subject_code,
                "semester": row.AcademicRecord.semester,
                "marks": float(row.AcademicRecord.marks),
                "grade": "N/A", 
                "is_pass": float(row.AcademicRecord.marks) >= 40,
                "status": "Pass" if float(row.AcademicRecord.marks) >= 40 else "Fail",
                "subject": row.subject_name,
            }
            for row in academic_rows
        ],
        "attendance": [
            {
                "subject": row.subject_name,
                "attendance_pct": float(row.AcademicRecord.attendance_percentage)
            }
            for row in academic_rows
        ],
        "pass_fail_ratio": {
            "pass": sum(1 for row in academic_rows if float(row.AcademicRecord.marks) >= 40),
            "fail": sum(1 for row in academic_rows if float(row.AcademicRecord.marks) < 40),
        },
        "risk": {
            "risk_score": risk.risk_score if risk else None,
            "suggestions": risk.suggestions if risk else None,
            "prediction_date": risk.prediction_date if risk else None,
        },
    }
