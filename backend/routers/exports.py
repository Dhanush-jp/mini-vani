import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from database.session import get_db
from models.entities import User
from schemas.common import StudentFilter
from services.exporter import export_single_student, export_students

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/students")
def export_filtered_students(
    filters: StudentFilter,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        content = export_students(db, current_user, filters)
    except SQLAlchemyError as exc:
        logger.exception("Export students failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not generate export file.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="students_export.xlsx"'},
    )


@router.post("/student/{student_id}")
def export_student(
    student_id: int,
    filters: StudentFilter,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        content = export_single_student(db, current_user, student_id, filters)
    except SQLAlchemyError as exc:
        logger.exception("Export single student failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not generate export file.") from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="student_{student_id}_export.xlsx"'},
    )
