import httpx
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from auth.deps import require_roles, get_current_user
from database.config import settings
from database.session import get_db
from models.entities import Attendance, AttendanceStatus, RiskAnalysis, SemesterResult, Student, User, UserRole
from schemas.common import SubjectOption
from schemas.api_response import StandardResponse
from services.analytics import build_student_dashboard
from services.student_me import build_student_me_response
from services.helpers import safe_percentage
from services.semester_history import build_semester_history, build_semester_comparison
from core.responses import success_response

router = APIRouter(prefix="/student", tags=["student"])
students_alias_router = APIRouter(prefix="/students", tags=["student"])

@students_alias_router.get("/{student_id}", response_model=StandardResponse)
def get_student_detail_full(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requirement 5: Return student + full subject list with marks."""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    from models.entities import AcademicRecord, Subject
    records = (
        db.query(AcademicRecord, Subject.name.label("subject_name"))
        .join(Subject, Subject.id == AcademicRecord.subject_id)
        .filter(AcademicRecord.student_id == student_id)
        .all()
    )
    
    # Format for frontend
    subject_list = []
    for row in records:
        entry = row.AcademicRecord.__dict__.copy()
        entry.pop("_sa_instance_state", None)
        entry["subject_name"] = row.subject_name
        subject_list.append(entry)

    data = {
        "student": student,
        "subjects": subject_list
    }
    return success_response(data, "Student details retrieved.")

@students_alias_router.get("/{student_id}/semester-history", response_model=StandardResponse)
def get_student_semester_history(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Teacher/Admin view of semester history."""
    data = build_semester_history(db, student_id)
    return success_response(data, "Semester history retrieved.")

@students_alias_router.get("/{student_id}/semester-compare", response_model=StandardResponse)
def get_student_semester_compare(student_id: int, sem_a: int, sem_b: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Teacher/Admin view of semester comparison."""
    data = build_semester_comparison(db, student_id, sem_a, sem_b)
    return success_response(data, "Semester comparison retrieved.")

class MlRiskResponse(BaseModel):
    risk_score: float = Field(ge=1, le=10)
    suggestions: str = Field(min_length=1, max_length=2048)

@router.get("/me", response_model=StandardResponse)
def get_current_student_profile(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    """Single payload: profile, summary, dashboard graphs, merged subjects (preferred for SPA bootstrap)."""
    payload = build_student_me_response(db, current_user)
    if not payload:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return success_response(payload, "Profile retrieved.")

@router.get("/{student_id}/subjects", response_model=StandardResponse[List[SubjectOption]])
def fetch_student_subjects(
    student_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from services.student_management import list_student_subjects
    data = list_student_subjects(db, student_id)
    return success_response(data, "Subjects retrieved.")

@router.get("/me/dashboard", response_model=StandardResponse)
def my_dashboard(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    data = build_student_dashboard(db, student.id)
    return success_response(data, "Dashboard data retrieved.")

@router.get("/me/summary", response_model=StandardResponse)
def my_summary(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    result = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student.id)
        .order_by(SemesterResult.semester.desc())
        .first()
    )
    total = db.query(Attendance).filter(Attendance.student_id == student.id).count()
    present = db.query(Attendance).filter(Attendance.student_id == student.id, Attendance.status == AttendanceStatus.PRESENT).count()
    attendance_pct = safe_percentage(present, total)
    data = {
        "student_id": student.id,
        "attendance_pct": attendance_pct,
        "sgpa": float(result.sgpa) if result else 0,
        "cgpa": float(result.cgpa) if result else 0,
        "backlogs": int(result.backlogs) if result else 0,
    }
    return success_response(data, "Summary retrieved.")

@router.post("/me/predict-risk", response_model=StandardResponse)
def predict_my_risk(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    result = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student.id)
        .order_by(SemesterResult.semester.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=400, detail="Semester result missing.")
    total = db.query(Attendance).filter(Attendance.student_id == student.id).count()
    present = db.query(Attendance).filter(Attendance.student_id == student.id, Attendance.status == AttendanceStatus.PRESENT).count()
    attendance_pct = safe_percentage(present, total)

    payload = {
        "attendance_pct": attendance_pct,
        "sgpa": float(result.sgpa),
        "cgpa": float(result.cgpa),
        "backlogs": int(result.backlogs),
    }
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{settings.ml_service_url}/predict-risk", json=payload)
            response.raise_for_status()
            raw = response.json()
            data = MlRiskResponse.model_validate(raw)
    except Exception as exc:
        logger.warning(f"ML risk prediction failed: {exc}")
        raise HTTPException(status_code=502, detail="ML service error.")

    risk_row = db.query(RiskAnalysis).filter(RiskAnalysis.student_id == student.id).first()
    if risk_row:
        risk_row.risk_score = data.risk_score
        risk_row.suggestions = data.suggestions
    else:
        db.add(RiskAnalysis(student_id=student.id, risk_score=data.risk_score, suggestions=data.suggestions))
    
    db.commit()
    return success_response(data.model_dump(), "Risk analysis completed.")

@router.get("/me/semester-history", response_model=StandardResponse)
def my_semester_history(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    data = build_semester_history(db, student.id)
    return success_response(data, "Semester history retrieved.")

@router.get("/me/semester-compare", response_model=StandardResponse)
def my_semester_compare(sem_a: int, sem_b: int, current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    data = build_semester_comparison(db, student.id, sem_a, sem_b)
    return success_response(data, "Semester comparison retrieved.")
