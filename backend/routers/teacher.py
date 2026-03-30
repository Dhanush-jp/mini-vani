from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from loguru import logger

from auth.deps import require_roles
from database.session import get_db
from models.entities import Attendance, Grade, SemesterResult, Subject, User, UserRole
from schemas.common import (
    AttendanceUpsert, 
    GradeUpsert, 
    SemesterResultUpsert, 
    StudentCreate, 
    StudentFilter, 
    StudentSubjectAssign,
    SubjectCreate
)
from schemas.api_response import StandardResponse
from services.access import assert_student_access
from services.analytics import apply_student_filters, build_student_dashboard
from services.grading import compute_grade, recompute_student_metrics
from services.student_management import (
    assign_subject_to_student, 
    build_dashboard_summary, 
    create_student, 
    get_student_record, 
    list_student_subjects, 
    list_students, 
    list_subjects
)
from core.responses import success_response

router = APIRouter(prefix="/teacher", tags=["teacher"])

@router.get("/bootstrap", response_model=StandardResponse)
def teacher_bootstrap(
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    filters = StudentFilter()
    data = {
        "summary": build_dashboard_summary(db, current_user, filters),
        "students": list_students(db, current_user, filters),
        "teachers": [],
        "subjects": list_subjects(db),
    }
    return success_response(data, "Teacher bootstrap data loaded.")

@router.get("/students", response_model=StandardResponse)
def teacher_students(
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
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
    return success_response(data, "Students retrieved successfully.")

@router.post("/students", status_code=status.HTTP_201_CREATED, response_model=StandardResponse)
def teacher_create_student(
    payload: StudentCreate,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    student = create_student(db, current_user, payload)
    return success_response(student, "Student created successfully.")

@router.get("/students/{student_id}", response_model=StandardResponse)
def teacher_student_detail(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    student = get_student_record(db, current_user, student_id)
    return success_response(student, "Student details retrieved.")

@router.get("/students/{student_id}/attendance", response_model=StandardResponse)
def attendance_history(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    assert_student_access(db, current_user, student_id)
    from models.entities import Subject
    rows = (
        db.query(Attendance.id, Attendance.student_id, Attendance.subject_id, Subject.name.label("subject_name"), Attendance.date, Attendance.status)
        .join(Subject, Subject.id == Attendance.subject_id)
        .filter(Attendance.student_id == student_id)
        .order_by(Attendance.date.desc())
        .all()
    )
    data = {"items": [dict(row._mapping) for row in rows]}
    return success_response(data, "Attendance history retrieved.")

@router.post("/attendance", response_model=StandardResponse)
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
    db.commit()
    return success_response(message="Attendance saved successfully.")

@router.post("/grades", response_model=StandardResponse)
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
    db.commit()
    return success_response({"grade": grade_value, "is_pass": is_pass}, "Grade saved successfully.")

@router.get("/students/{student_id}/subjects", response_model=StandardResponse)
def get_student_subjects(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Retrieve all subjects currently assigned to a student."""
    assert_student_access(db, current_user, student_id)
    data = list_student_subjects(db, student_id)
    return success_response(data, "Student subjects retrieved.")

@router.post("/students/{student_id}/subjects", response_model=StandardResponse)
def add_or_update_subject(
    student_id: int,
    payload: SubjectCreate,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Requirement: Add or update a subject record (marks/attendance) for a student."""
    assert_student_access(db, current_user, student_id)
    
    from models.entities import AcademicRecord, Subject
    from datetime import datetime

    # 1. Resolve Subject catalog entry
    subject = None
    if payload.subject_id:
        subject = db.query(Subject).filter(Subject.id == payload.subject_id).first()
    
    if not subject and payload.subject_name:
        subj_name = payload.subject_name.strip()
        subject = db.query(Subject).filter(Subject.name == subj_name, Subject.semester == payload.semester).first()
        
        if not subject:
            # Create a new subject code deterministically
            code_prefix = "".join(w[0].upper() for w in subj_name.split()[:3] if w)
            code = f"{code_prefix}{payload.semester:02d}"
            subject = Subject(name=subj_name, code=code, semester=payload.semester)
            db.add(subject)
            db.flush()
            logger.info(f"Auto-created subject catalog entry: {subj_name} ({code})")
    
    if not subject:
        raise HTTPException(status_code=400, detail="Must provide either a valid subject_id or a subject_name.")

    # 2. Resolve AcademicRecord (student link + data)
    existing = db.query(AcademicRecord).filter_by(
        student_id=student_id,
        subject_id=subject.id,
        semester=payload.semester
    ).first()

    action = "updated" if existing else "created"
    
    if existing:
        existing.marks = payload.marks
        existing.attendance_percentage = payload.attendance_percentage
        existing.last_updated_at = datetime.utcnow()
    else:
        existing = AcademicRecord(
            student_id=student_id,
            subject_id=subject.id,
            semester=payload.semester,
            marks=payload.marks,
            attendance_percentage=payload.attendance_percentage,
            last_updated_at=datetime.utcnow(),
            updated_by_import=False
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)
    
    logger.info(f"Subject {action} for Student ID {student_id}: {subject.name}")

    data = {
        "id": existing.id,
        "subject_name": subject.name,
        "marks": existing.marks,
        "attendance_percentage": existing.attendance_percentage,
        "action": action
    }
    
    return success_response(data, f"Subject {action} successfully.")

@router.get("/students/{student_id}/results", response_model=StandardResponse)
def get_student_results_flat(
    student_id: int,
    current_user: User = Depends(require_roles(UserRole.TEACHER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    """Requirement 2: Return flat list of marks and attendance for charts."""
    assert_student_access(db, current_user, student_id)
    
    from models.entities import AcademicRecord, Subject
    records = (
        db.query(
            AcademicRecord, 
            Subject.name.label("subject_name"),
            Subject.code.label("subject_code")
        )
        .join(Subject, Subject.id == AcademicRecord.subject_id)
        .filter(AcademicRecord.student_id == student_id)
        .all()
    )
    
    # Requirement 2 & 4: Flat format + empty list handle + safe mapping
    results = []
    for row in records:
        ar = row.AcademicRecord
        results.append({
            "id": ar.id,
            "subject_name": row.subject_name,
            "subject_code": row.subject_code,
            "subject": row.subject_name, 
            "code": row.subject_code,    
            "marks": float(ar.marks),
            "attendance": float(ar.attendance_percentage),
            "semester": ar.semester,
            "is_pass": float(ar.marks) >= 40,
            "status": "Pass" if float(ar.marks) >= 40 else "Fail"
        })
    
    logger.info(f"Final results payload for {student_id}: {len(results)} items.")
    if results:
        logger.info(f"Keys in first item: {list(results[0].keys())}")
        logger.info(f"Values in first item: {results[0]}")
    
    return success_response(results, "Student results retrieved.")
