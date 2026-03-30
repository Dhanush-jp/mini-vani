from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class ImportErrorItem(BaseModel):
    row: int
    error: str

class ImportResult(BaseModel):
    audit_id: int
    status: str
    message: str

class AuditSummary(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    uploaded_by: Optional[str] = None
    status: str
    total_rows: int
    created: int
    updated: int
    skipped: int
    failed: int

    class Config:
        from_attributes = True

class AuditDetail(AuditSummary):
    errors: List[ImportErrorItem]
