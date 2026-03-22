import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth.deps import require_roles
from database.session import get_db
from models.entities import TeacherStudent, User, UserRole
from schemas.common import StudentCreate, StudentFilter
from services.analytics import apply_student_filters
from services.student_management import build_dashboard_summary, create_student, get_student_record, list_students, list_subjects, list_teachers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/teacher-assignments")
def assign_teacher_student(
    teacher_id: int,
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    db.query(TeacherStudent).filter(TeacherStudent.student_id == student_id).delete()
    db.add(TeacherStudent(teacher_id=teacher_id, student_id=student_id))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Teacher-student assignment conflict: %s", exc)
        raise HTTPException(status_code=409, detail="Invalid teacher or student id, or mapping already exists.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("DB error assigning teacher-student: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save assignment.") from exc
    return {"message": "Teacher assigned to student."}


@router.get("/bootstrap")
def admin_bootstrap(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    filters = StudentFilter()
    return {
        "summary": build_dashboard_summary(db, current_user, filters),
        "students": list_students(db, current_user, filters),
        "teachers": list_teachers(db),
        "subjects": list_subjects(db),
    }


@router.get("/students")
def admin_students(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
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
def admin_create_student(
    payload: StudentCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return create_student(db, current_user, payload)


@router.get("/students/{student_id}")
def admin_student_detail(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_student_record(db, current_user, student_id)


@router.post("/students/filter")
def filter_all_students(
    filters: StudentFilter,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    ids = list(apply_student_filters(db, current_user, filters))
    return {"student_ids": ids}
