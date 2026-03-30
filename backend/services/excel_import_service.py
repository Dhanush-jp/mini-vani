import io
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from models.entities import ImportAudit, ImportStatus, User
from schemas.excel_row import ExcelRow
from services.academic_repository import (
    create_import_audit,
    ensure_student_subject_link,
    ensure_teacher_link,
    get_or_create_student,
    get_or_create_subject,
    load_record_cache_scoped,
    load_student_cache_scoped,
    load_subject_cache,
    resolve_teacher,
    upsert_academic_record,
    upsert_semester_result,
)

@dataclass
class ImportStats:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def add_error(self, row: int, msg: str):
        self.failed += 1
        self.errors.append({"row": row, "error": msg})
        logger.warning(f"Row {row} failed: {msg}")

async def start_asynchronous_import(
    db: Session,
    current_user: User,
    filename: str,
    content: bytes,
    teacher_id: Optional[int] = None,
) -> int:
    """Creates a PENDING audit record and returns its ID."""
    audit = create_import_audit(
        db,
        uploaded_by_id=current_user.id,
        filename=filename,
        status=ImportStatus.PENDING,
    )
    db.commit()
    logger.info(f"Initiated import for {filename} (Audit ID: {audit.id})")
    return audit.id

def process_excel_background_task(
    db_factory: Any,
    audit_id: int,
    filename: str,
    content: bytes,
    teacher_user_id: int,
    teacher_id_form: Optional[int] = None,
) -> None:
    """Production-grade Excel processing background worker with chunking and live updates."""
    db: Session = db_factory()
    stats = ImportStats()
    
    try:
        audit = db.get(ImportAudit, audit_id)
        if not audit:
            logger.error(f"Audit {audit_id} not found in background task")
            return
            
        user = db.get(User, teacher_user_id)
        if not user:
            logger.error(f"User {teacher_user_id} not found in background task")
            return

        audit.status = ImportStatus.PROCESSING
        db.commit()
        
        logger.info(f"Starting background processing for Audit {audit_id}...")
        start_time = time.time()

        # 1. Read Excel optimally
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            logger.info(f"READ SUCCESS: {filename} - {len(df)} rows found.")
        except Exception as e:
            _fail_audit(db, audit, f"Failed to read Excel file: {str(e)}")
            logger.error(f"PANDAS READ ERROR: {str(e)}")
            return

        # 2. Normalize and Map Columns (Requirement 1 & 2)
        try:
            df.columns = df.columns.astype(str).str.strip().str.lower()
            column_mapping = {
                "name": "student_name", "student name": "student_name", "student": "student_name",
                "roll no": "roll_number", "roll_no": "roll_number", "roll number": "roll_number", 
                "rollnumber": "roll_number", "roll_number": "roll_number",
                "dept": "department", "department": "department",
                "sem": "semester", "semester": "semester",
                "sub": "subject", "subject": "subject",
                "scores": "marks", "marks": "marks",
                "attendance": "attendance", "attendance %": "attendance", 
                "attendance_percentage": "attendance",
                "backlogs": "backlogs", "history of backlogs": "backlogs",
                "detained": "detained",
                "email": "email", "e-mail": "email",
                "year": "year", "year_of_study": "year",
                "section": "section", "class": "section",
                "cgpa": "cgpa", "sgpa": "sgpa"
            }
            df.rename(columns=column_mapping, inplace=True)
            logger.info(f"Columns after normalization & mapping: {df.columns.tolist()}")

            # 3. Handle Missing Columns (Requirement 3 & 4 & 8)
            default_values = {
                "student_name": "Unknown",
                "email": None,
                "roll_number": None,
                "department": "General",
                "section": "A",
                "cgpa": 0.0,
                "sgpa": 0.0,
                "year": 1,
                "semester": 1,
                "subject": "General",
                "marks": 0.0,
                "attendance": 0.0,
                "backlogs": 0,
                "detained": False
            }
            
            missing_cols = []
            for col, default in default_values.items():
                if col not in df.columns:
                    logger.warning(f"Column missing: {col}, filling with default: {default}")
                    df[col] = default
                    missing_cols.append(col)
            
            if missing_cols:
                stats.add_error(0, f"Warning: These columns were missing and filled with defaults: {missing_cols}")

        except Exception as e:
            logger.exception("Error during column processing")
            _fail_audit(db, audit, f"Column processing failed: {str(e)}")
            return

        stats.total_rows = len(df)
        audit.total_rows = stats.total_rows
        db.commit()

        # 3. Pre-load Caches
        teacher = resolve_teacher(db, user, teacher_id_form)
        unique_rolls = df["roll_number"].dropna().unique().tolist()
        unique_subjects = df["subject"].dropna().unique().tolist()

        student_cache = load_student_cache_scoped(db, unique_rolls)
        subject_cache = load_subject_cache(db, unique_subjects)
        student_ids = [s.id for s in student_cache.values()]
        record_cache = load_record_cache_scoped(db, student_ids)

        # 4. Row-by-row processing
        for idx, row_data in df.iterrows():
            row_num = idx + 2
            
            if time.time() - start_time > 900: # 15 min safety
                _fail_audit(db, audit, "Processing timeout.")
                return

            if idx % 1000 == 0 and idx > 0:
                logger.info(f"Progress: {idx}/{stats.total_rows} for Audit {audit_id}")
                audit.created = stats.created
                audit.updated = stats.updated
                audit.failed = stats.failed
                audit.skipped = stats.skipped
                db.commit()

            if row_data.isnull().all():
                stats.total_rows -= 1
                continue
                
            try:
                # Requirement 5 & 8: Safe row processing
                clean_data = row_data.to_dict()
                for k, v in clean_data.items():
                    if pd.isna(v): clean_data[k] = None
                
                # Critical field: roll_number is ONLY identifier. 
                # Student name has default "Unknown". Email has special logic.
                roll_number = clean_data.get("roll_number")
                if not roll_number:
                    logger.warning(f"Row {idx} skipped: missing roll_number")
                    stats.skipped += 1
                    continue

                # Dummy email if missing (needed for DB uniqueness)
                if not clean_data.get("email"):
                    clean_data["email"] = f"{roll_number}@student.edu"
                
                # Internal 'student_name' -> schema 'name'
                if "student_name" in clean_data:
                    clean_data["name"] = clean_data.pop("student_name")
                
                parsed = ExcelRow(**clean_data)

                # B. Database Logic
                with db.begin_nested():
                    # Get/Create student
                    student, created_student = get_or_create_student(
                        db, student_cache,
                        name=parsed.name, email=parsed.email,
                        department=parsed.department, year=parsed.year,
                        section=parsed.section, roll_number=parsed.roll_number,
                        cgpa=parsed.cgpa or 0.0, sgpa=parsed.sgpa or 0.0
                    )
                    if created_student:
                        logger.info(f"Student processed (CREATED): {parsed.roll_number}")
                    else:
                        logger.info(f"Student processed (UPDATED): {parsed.roll_number}")

                    ensure_teacher_link(db, student, teacher)

                    # Get/Create subject
                    subject = get_or_create_subject(db, subject_cache, name=parsed.subject, semester=parsed.semester)
                    ensure_student_subject_link(db, student, subject)

                    # Upsert academic record (Subject record)
                    outcome = upsert_academic_record(
                        db, record_cache,
                        student_id=student.id, subject_id=subject.id,
                        semester=parsed.semester, marks=parsed.marks,
                        attendance_percentage=parsed.attendance,
                        backlogs=parsed.backlogs, detained=parsed.detained
                    )
                    
                    if outcome == "created": 
                        stats.created += 1
                        logger.info(f"Subject {parsed.subject} created for Student {parsed.roll_number}")
                    elif outcome == "updated": 
                        stats.updated += 1
                        logger.info(f"Subject {parsed.subject} updated for Student {parsed.roll_number}")
                    else: 
                        stats.skipped += 1
                        logger.info(f"Subject processed (UNCHANGED): {parsed.subject}")

                    # Upsert semester-level GPA if provided
                    upsert_semester_result(
                        db, student_id=student.id, semester=parsed.semester,
                        sgpa=parsed.sgpa, cgpa=parsed.cgpa, backlogs=parsed.backlogs
                    )
                
                logger.info(f"Row {idx} processed successfully")

                if (idx + 1) % 500 == 0:
                    db.flush()

            except Exception as e:
                db.rollback()
                stats.add_error(row_num, str(e))

        # 5. Finalize
        audit.status = ImportStatus.COMPLETED
        audit.created = stats.created
        audit.updated = stats.updated
        audit.skipped = stats.skipped
        audit.failed = stats.failed
        audit.errors_json = json.dumps(stats.errors[:1000])
        db.commit()
        logger.info(f"Import {audit_id} finished. Created: {stats.created}, Updated: {stats.updated}")

    except Exception as e:
        logger.exception(f"Critical failure in background task for Audit {audit_id}")
        _fail_audit(db, audit, f"System error: {str(e)}")
    finally:
        db.close()

def _fail_audit(db: Session, audit: ImportAudit, message: str):
    """Safely mark an audit as failed."""
    try:
        audit.status = ImportStatus.FAILED
        errors = json.loads(audit.errors_json) if audit.errors_json else []
        errors.append({"row": 0, "error": message})
        audit.errors_json = json.dumps(errors[:10])
        db.commit()
    except:
        db.rollback()
        logger.error("Could not update audit status to FAILED")
