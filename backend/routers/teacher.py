import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth.deps import require_roles
from database.session import get_db
from models.entities import Attendance, Grade, SemesterResult, Subject, User, UserRole
from schemas.common import AttendanceUpsert, GradeUpsert, SemesterResultUpsert, StudentCreate, StudentFilter, StudentSubjectAssign
from services.access import assert_student_access
from services.analytics import apply_student_filters, build_student_dashboard
from services.grading import compute_grade, recompute_student_metrics
from services.student_management import assign_subject_to_student, build_dashboard_summary, create_student, get_student_record, list_student_subjects, list_students, list_subjects

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teacher", tags=["teacher"])


def _commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Integrity error on teacher write: %s", exc)
        raise HTTPException(status_code=409, detail="Data conflict (duplicate or invalid reference).") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error on teacher write: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save changes.") from exc


@router.get("/bootstrap")
def teacher_bootstrap(
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    filters = StudentFilter()
    return {
        "summary": build_dashboard_summary(db, current_user, filters),
        "students": list_students(db, current_user, filters),
        "teachers": [],
        "subjects": list_subjects(db),
    }


@router.get("/students")
def teacher_students(
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
    department: str | None = None,
    year: int | None = None,
    section: str | None = None,
    cgpa_min: float | None = None,
    cgpa_max: float | None = None,
    risk_level: str | None = None,
    search: str | None = None,
):
    filters = StudentFilter(
        department=department,
        year=year,
        section=section,
        cgpa_min=cgpa_min,
        cgpa_max=cgpa_max,
        risk_level=risk_level,
        search=search,
    )
    return list_students(db, current_user, filters)


@router.post("/students", status_code=201)
def teacher_create_student(
    payload: StudentCreate,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return create_student(db, current_user, payload)


@router.get("/students/{student_id}")
def teacher_student_detail(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_student_record(db, current_user, student_id)


@router.get("/students/{student_id}/attendance")
def attendance_history(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    rows = (
        db.query(Attendance.id, Attendance.student_id, Attendance.subject_id, Subject.name.label("subject_name"), Attendance.date, Attendance.status)
        .join(Subject, Subject.id == Attendance.subject_id)
        .filter(Attendance.student_id == student_id)
        .order_by(Attendance.date.desc())
        .all()
    )
    return {"items": [dict(row._mapping) for row in rows]}


@router.get("/students/{student_id}/results")
def result_history(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    rows = (
        db.query(
            Grade.id,
            Grade.student_id,
            Grade.subject_id,
            Subject.name.label("subject_name"),
            Subject.code.label("subject_code"),
            Grade.semester,
            Grade.marks,
            Grade.grade,
            Grade.is_pass,
        )
        .join(Subject, Subject.id == Grade.subject_id)
        .filter(Grade.student_id == student_id)
        .order_by(Grade.semester.asc(), Subject.name.asc())
        .all()
    )
    return {
        "items": [
            {
                **dict(row._mapping),
                "marks": float(row.marks),
            }
            for row in rows
        ]
    }


@router.get("/students/{student_id}/subjects")
def student_subjects(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    return {"items": list_student_subjects(db, student_id)}


@router.post("/students/{student_id}/subjects")
def add_student_subject(
    student_id: int,
    payload: StudentSubjectAssign,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    if payload.student_id != student_id:
        raise HTTPException(status_code=400, detail="Student id mismatch.")
    assign_subject_to_student(db, student_id, payload.subject_id)
    _commit_or_rollback(db)
    return {"message": "Subject assigned to student."}


@router.post("/attendance")
def upsert_attendance(
    payload: AttendanceUpsert,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, payload.student_id)
    row = (
        db.query(Attendance)
        .filter(
            Attendance.student_id == payload.student_id,
            Attendance.subject_id == payload.subject_id,
            Attendance.date == payload.date,
        )
        .first()
    )
    if row:
        row.status = payload.status
    else:
        db.add(Attendance(**payload.model_dump()))
    db.flush()
    recompute_student_metrics(db, payload.student_id)
    _commit_or_rollback(db)
    return {"message": "Attendance saved."}


@router.post("/grades")
def upsert_grade(
    payload: GradeUpsert,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, payload.student_id)
    grade_value, is_pass = compute_grade(payload.marks)
    row = (
        db.query(Grade)
        .filter(
            Grade.student_id == payload.student_id,
            Grade.subject_id == payload.subject_id,
            Grade.semester == payload.semester,
        )
        .first()
    )
    if row:
        row.marks = payload.marks
        row.grade = grade_value
        row.is_pass = is_pass
    else:
        db.add(Grade(**payload.model_dump(), grade=grade_value, is_pass=is_pass))
    db.flush()
    recompute_student_metrics(db, payload.student_id)
    _commit_or_rollback(db)
    return {"message": "Grade saved.", "grade": grade_value, "is_pass": is_pass}


@router.post("/semester-result")
def upsert_semester_result(
    payload: SemesterResultUpsert,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, payload.student_id)
    row = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == payload.student_id, SemesterResult.semester == payload.semester)
        .first()
    )
    if row:
        row.sgpa = payload.sgpa
        row.cgpa = payload.cgpa
        row.backlogs = payload.backlogs
    else:
        db.add(SemesterResult(**payload.model_dump()))
    _commit_or_rollback(db)
    return {"message": "Semester result saved."}


@router.post("/students/filter")
def filtered_students(
    filters: StudentFilter,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    ids = list(apply_student_filters(db, current_user, filters))
    return {"student_ids": ids}


@router.get("/students/{student_id}/analytics")
def student_analytics(student_id: int, current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)), db: Session = Depends(get_db)):
    assert_student_access(db, current_user, student_id)
    return build_student_dashboard(db, student_id)
