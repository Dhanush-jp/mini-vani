import json
import traceback
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload
from loguru import logger

from auth.deps import require_roles
from database.session import SessionLocal, get_db
from models.entities import ImportAudit, ImportStatus, User, UserRole
from schemas.import_audit import ImportResult, AuditSummary, AuditDetail, ImportErrorItem
from schemas.api_response import StandardResponse
from services.excel_import_service import process_excel_background_task, start_asynchronous_import

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm", ".csv"}

router = APIRouter(prefix="/import", tags=["import"])

@router.post(
    "/excel",
    response_model=StandardResponse[ImportResult],
    summary="Upload & import students from Excel (intelligent diff detection)",
)
async def upload_academic_excel(
    file: UploadFile = File(..., description="Excel file (.xlsx/.xlsm) with academic data"),
    teacher_id: int | None = Form(default=None, description="Assign new students to this teacher ID (ADMIN only)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER)),
    db: Session = Depends(get_db),
):
    """
    **Intelligent Excel Import**
    Initiates a background task to process the uploaded file.
    """
    logger.info(f"Received file: {file.filename}")

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File name is missing.")

    if not file.filename.lower().endswith((".xlsx", ".xlsm", ".csv")):
        logger.warning(f"Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid file type. Only .xlsx, .xlsm, and .csv are allowed.")

    content = await file.read()
    await file.close()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    try:
        # 1. Initiate record and get ID
        logger.info(f"Initiating audit for {file.filename}...")
        audit_id = await start_asynchronous_import(
            db=db,
            current_user=current_user,
            filename=file.filename,
            content=content,
            teacher_id=teacher_id,
        )

        logger.info(f"Spawning background task for Audit ID: {audit_id}")
        # 2. Spawn background task
        background_tasks.add_task(
            process_excel_background_task,
            db_factory=lambda: SessionLocal(),
            audit_id=audit_id,
            filename=file.filename,
            content=content,
            teacher_user_id=current_user.id,
            teacher_id_form=teacher_id,
        )
        
        return StandardResponse(
            success=True,
            message="Import process started successfully.",
            data=ImportResult(
                audit_id=audit_id,
                status="PENDING",
                message="File uploaded. Processing will continue in the background."
            )
        )
    except Exception as exc:
        traceback.print_exc()
        logger.error(f"UPLOAD ERROR for {file.filename}: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel upload failed: {str(exc)}"
        )

@router.get(
    "/audits",
    response_model=StandardResponse[List[AuditSummary]],
    summary="List recent import audit logs",
)
def list_import_audits(
    limit: int = 50,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER)),
    db: Session = Depends(get_db),
):
    """Return the most recent `limit` import audit records, newest first."""
    query = db.query(ImportAudit)
    if current_user.role == UserRole.TEACHER:
        query = query.filter(ImportAudit.uploaded_by_id == current_user.id)

    audits = (
        query.options(joinedload(ImportAudit.uploaded_by))
        .order_by(ImportAudit.uploaded_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    
    data = [_audit_to_summary(a) for a in audits]
    return StandardResponse(success=True, message="Audit logs retrieved.", data=data)

@router.get(
    "/audits/{audit_id}",
    response_model=StandardResponse[AuditDetail],
    summary="Detail view of a single import audit log",
)
def get_import_audit(
    audit_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER)),
    db: Session = Depends(get_db),
):
    audit = db.query(ImportAudit).options(joinedload(ImportAudit.uploaded_by)).filter(ImportAudit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Audit {audit_id} not found.")

    if current_user.role == UserRole.TEACHER and audit.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    summary = _audit_to_summary(audit)
    errors: List[ImportErrorItem] = []
    if audit.errors_json:
        try:
            raw = json.loads(audit.errors_json)
            errors = [ImportErrorItem(**e) for e in raw]
        except Exception:
            pass

    detail = AuditDetail(**summary.model_dump(), errors=errors)
    return StandardResponse(success=True, message="Audit detail retrieved.", data=detail)

def _audit_to_summary(audit: ImportAudit) -> AuditSummary:
    uploader_name = audit.uploaded_by.name if audit.uploaded_by else None

    return AuditSummary(
        id=audit.id,
        filename=audit.filename,
        uploaded_at=audit.uploaded_at,
        uploaded_by=uploader_name,
        total_rows=audit.total_rows,
        created=audit.created,
        updated=audit.updated,
        skipped=audit.skipped,
        failed=audit.failed,
        status=audit.status.value,
    )
