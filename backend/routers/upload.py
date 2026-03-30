import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth.deps import require_roles
from database.session import get_db
from models.entities import User, UserRole
from services.upload_service import process_excel_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/excel")
async def upload_excel(
    file: UploadFile = File(...),
    teacher_id: int | None = Form(default=None),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER)),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File name is missing.")
    if file.content_type not in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/octet-stream",  # some browsers fallback to octet-stream
    }:
        # Keep extension check in service as final authority.
        logger.info("Upload content_type=%s filename=%s", file.content_type, file.filename)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 10MB).")

    try:
        result = process_excel_upload(
            db=db,
            current_user=current_user,
            filename=file.filename,
            content=content,
            teacher_id=teacher_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Excel upload failed unexpectedly: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process uploaded Excel file.") from exc
    finally:
        await file.close()

    return result
