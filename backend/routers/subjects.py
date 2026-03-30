from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from loguru import logger

from database.session import get_db
from models.entities import User, UserRole, Subject, StudentSubject, Student
from auth.deps import require_roles
from schemas.common import SubjectOption
from schemas.api_response import StandardResponse
from services.student_management import list_subjects
from core.responses import success_response

router = APIRouter(prefix="/subjects", tags=["subjects"])

class SubjectCreate(BaseModel):
    name: str
    code: str
    semester: int

class SubjectAssign(BaseModel):
    student_id: int
    subject_id: int

@router.post("", response_model=StandardResponse[SubjectOption], status_code=status.HTTP_201_CREATED)
def create_subject(
    payload: SubjectCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    existing = db.query(Subject).filter(Subject.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Subject code already exists.")
    
    subject = Subject(name=payload.name, code=payload.code, semester=payload.semester)
    db.add(subject)
    try:
        db.commit()
        db.refresh(subject)
        data = SubjectOption(id=subject.id, name=subject.name, code=subject.code, semester=subject.semester)
        return success_response(data, "Subject created successfully.")
    except Exception as e:
        db.rollback()
        logger.exception("Failed to create subject")
        raise HTTPException(status_code=500, detail="Failed to create subject.")

@router.get("", response_model=StandardResponse[List[SubjectOption]])
def get_subjects(
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT)),
    db: Session = Depends(get_db),
):
    data = list_subjects(db)
    return success_response(data, "Subjects list retrieved.")

@router.post("/assign", response_model=StandardResponse)
def assign_subject(
    payload: SubjectAssign,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER)),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.id == payload.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
        
    subject = db.query(Subject).filter(Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")
        
    existing = db.query(StudentSubject).filter(
        StudentSubject.student_id == payload.student_id,
        StudentSubject.subject_id == payload.subject_id
    ).first()
    if existing:
        return success_response(message="Subject already assigned to student.")
    
    try:
        db.add(StudentSubject(student_id=payload.student_id, subject_id=payload.subject_id))
        db.commit()
        return success_response(message="Subject assigned successfully.")
    except Exception as e:
        db.rollback()
        logger.exception("Failed to assign subject")
        raise HTTPException(status_code=500, detail="Assign attempt failed.")

@router.delete("/{subject_id}", response_model=StandardResponse)
def delete_subject(
    subject_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")
    
    try:
        db.delete(subject)
        db.commit()
        return success_response(message="Subject deleted successfully.")
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to delete subject {subject_id}")
        raise HTTPException(status_code=500, detail="Delete operation failed.")
