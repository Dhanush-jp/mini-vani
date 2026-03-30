from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from schemas import ImportReport
from services.import_service import ImportService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/excel", response_model=ImportReport)
async def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportReport:
    logger.info("Received upload request for file '%s'.", file.filename)
    service = ImportService(db=db)
    return await service.import_excel(file)
