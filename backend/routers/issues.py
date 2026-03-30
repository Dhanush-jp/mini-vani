import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.deps import require_roles
from database.session import get_db
from models.entities import Issue, User, UserRole
from pydantic import BaseModel
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues", tags=["issues"])

class IssueCreate(BaseModel):
    title: str
    description: str

class IssueResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    title: str
    description: str
    timestamp: datetime

    class Config:
        from_attributes = True

@router.post("", status_code=status.HTTP_201_CREATED)
def create_issue(
    payload: IssueCreate,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT)),
    db: Session = Depends(get_db),
):
    try:
        new_issue = Issue(
            user_id=current_user.id,
            title=payload.title,
            description=payload.description
        )
        db.add(new_issue)
        db.commit()
        return {"message": "Issue reported successfully."}
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create issue")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to report issue."
        )

@router.get("", response_model=List[IssueResponse])
def get_issues(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    issues = db.query(Issue).order_by(Issue.timestamp.desc()).all()
    return [
        IssueResponse(
            id=issue.id,
            user_id=issue.user_id,
            user_name=issue.user.name,
            title=issue.title,
            description=issue.description,
            timestamp=issue.timestamp
        )
        for issue in issues
    ]
