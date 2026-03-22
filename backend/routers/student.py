import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth.deps import require_roles
from database.config import settings
from database.session import get_db
from models.entities import Attendance, AttendanceStatus, RiskAnalysis, SemesterResult, Student, User, UserRole
from services.analytics import build_student_dashboard
from services.student_me import build_student_me_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student", tags=["student"])
students_alias_router = APIRouter(prefix="/students", tags=["student"])


class MlRiskResponse(BaseModel):
    risk_score: float = Field(ge=1, le=10)
    suggestions: str = Field(min_length=1, max_length=2048)


def _student_me_or_404(db: Session, current_user: User) -> dict:
    payload = build_student_me_response(db, current_user)
    if not payload:
        logger.warning("student/me: 404 user_id=%s (no Student row)", current_user.id)
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return payload


@router.get("/me")
def get_current_student_profile(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    """Single payload: profile, summary, dashboard graphs, merged subjects (preferred for SPA bootstrap)."""
    return _student_me_or_404(db, current_user)


@students_alias_router.get("/me")
def get_current_student_profile_alias(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    """Alias: GET /students/me — same as GET /student/me."""
    return _student_me_or_404(db, current_user)


@router.get("/me/dashboard")
def my_dashboard(current_user: User = Depends(require_roles(UserRole.STUDENT)), db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    return build_student_dashboard(db, student.id)


@router.get("/me/summary")
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
    attendance_pct = round((present * 100.0 / total), 2) if total else 0
    return {
        "student_id": student.id,
        "attendance_pct": attendance_pct,
        "sgpa": float(result.sgpa) if result else 0,
        "cgpa": float(result.cgpa) if result else 0,
        "backlogs": int(result.backlogs) if result else 0,
    }


@router.post("/me/predict-risk")
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
    present = (
        db.query(Attendance)
        .filter(Attendance.student_id == student.id, Attendance.status == AttendanceStatus.PRESENT)
        .count()
    )
    attendance_pct = (present * 100.0 / total) if total else 0.0

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
            try:
                raw = response.json()
            except ValueError as exc:
                raise HTTPException(status_code=502, detail="ML service returned non-JSON body.") from exc
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.warning("ML service call failed: %s", exc)
        raise HTTPException(status_code=502, detail="ML service unavailable.") from exc

    try:
        data = MlRiskResponse.model_validate(raw)
    except Exception as exc:
        logger.warning("ML response validation failed: %s raw=%s", exc, raw)
        raise HTTPException(status_code=502, detail="ML service returned invalid payload.") from exc

    risk_row = db.query(RiskAnalysis).filter(RiskAnalysis.student_id == student.id).first()
    if risk_row:
        risk_row.risk_score = data.risk_score
        risk_row.suggestions = data.suggestions
    else:
        db.add(RiskAnalysis(student_id=student.id, risk_score=data.risk_score, suggestions=data.suggestions))
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to persist risk analysis: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save risk analysis.") from exc

    return data.model_dump()
