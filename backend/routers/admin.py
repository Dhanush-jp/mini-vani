from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from loguru import logger

from auth.deps import require_roles
from database.session import get_db
from models.entities import TeacherStudent, User, UserRole
from schemas.common import StudentCreate, StudentFilter
from schemas.api_response import StandardResponse
from services.analytics import apply_student_filters
from services.student_management import (
    build_dashboard_summary, 
    create_student, 
    get_student_record, 
    list_students, 
    list_subjects, 
    list_teachers
)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/bootstrap", response_model=StandardResponse)
def admin_bootstrap(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    try:
        filters = StudentFilter()
        data = {
            "summary": build_dashboard_summary(db, current_user, filters),
            "students": list_students(db, current_user, filters),
            "teachers": list_teachers(db),
            "subjects": list_subjects(db),
        }
        return StandardResponse(success=True, message="Bootstrap data loaded.", data=data)
    except Exception as e:
        logger.exception("Admin bootstrap failed")
        raise HTTPException(status_code=500, detail="Failed to load admin dashboard data.")

@router.get("/students", response_model=StandardResponse)
def admin_students(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
    department: Optional[str] = None,
    year: Optional[int] = None,
    section: Optional[str] = None,
    cgpa_min: Optional[float] = None,
    cgpa_max: Optional[float] = None,
    risk_level: Optional[str] = None,
    search: Optional[str] = None,
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
    data = list_students(db, current_user, filters)
    return StandardResponse(success=True, message="Student list retrieved.", data=data)

@router.post("/students", status_code=status.HTTP_201_CREATED, response_model=StandardResponse)
def admin_create_student(
    payload: StudentCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    student = create_student(db, current_user, payload)
    return StandardResponse(success=True, message="Student created successfully.", data=student)

@router.get("/students/{student_id}", response_model=StandardResponse)
def admin_student_detail(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    student = get_student_record(db, current_user, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    return StandardResponse(success=True, message="Student details retrieved.", data=student)

@router.post("/teacher-assignments", response_model=StandardResponse)
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
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to assign teacher: {exc}")
        raise HTTPException(status_code=400, detail="Assignment failed. Verify IDs.")
        
    return StandardResponse(success=True, message="Teacher assigned to student successfully.")
