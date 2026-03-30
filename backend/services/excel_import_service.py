from __future__ import annotations

import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import httpx
import pandas as pd
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from database.config import settings
from models.entities import AttendanceStatus, ImportAudit, ImportStatus, User
from services.academic_repository import (
    calculate_attendance_percentage,
    create_import_audit,
    ensure_student_subject_link,
    ensure_teacher_link,
    get_or_create_student,
    get_or_create_subject,
    load_attendance_cache_scoped,
    load_record_cache_scoped,
    load_student_cache_scoped,
    load_subject_cache,
    resolve_teacher,
    upsert_academic_record,
    upsert_attendance_record,
    upsert_semester_result,
)


SAMPLE_ROW_LIMIT = 10
HEADER_SCAN_LIMIT = 12
ATTENDANCE_FALLBACK_SUBJECT = "Daily Attendance"
ATTENDANCE_FALLBACK_SEMESTER = 0

BASE_MAPPING_FIELDS = {
    "roll_number",
    "student_name",
    "email",
    "department",
    "section",
    "year",
    "semester",
    "subject",
    "marks",
    "attendance",
    "percentage",
    "cgpa",
    "sgpa",
    "backlogs",
    "detained",
    "date",
    "ignore",
}
PREFIX_MAPPINGS = ("subject_marks:", "subject_attendance:", "subject_percentage:")


class FileType(str, Enum):
    MARKS = "marks"
    ATTENDANCE = "attendance"
    MIXED = "mixed"


class SheetFormat(str, Enum):
    WIDE = "wide"
    LONG = "long"
    DAILY = "daily"
    SUMMARY = "summary"


class ValueType(str, Enum):
    MARKS = "marks"
    ATTENDANCE = "attendance"
    PERCENTAGE = "percentage"


class AIStructureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header_row_index: int = Field(ge=0)
    primary_key: str
    file_type: FileType
    format: SheetFormat
    columns: dict[str, str]
    subjects: list[str] = Field(default_factory=list)
    value_type: ValueType
    attendance_values: list[str] = Field(default_factory=list)
    has_dates: bool

    @field_validator("primary_key")
    @classmethod
    def validate_primary_key(cls, value: str) -> str:
        normalized = normalize_column_name(value)
        if not normalized:
            raise ValueError("primary_key must be a non-empty string.")
        return normalized

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for source, target in value.items():
            normalized_source = normalize_column_name(source)
            normalized_target = normalize_mapping_value(target)
            parse_mapping_value(normalized_target)
            cleaned[normalized_source] = normalized_target
        return cleaned

    @field_validator("subjects")
    @classmethod
    def validate_subjects(cls, value: list[str]) -> list[str]:
        subjects: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = " ".join(str(item).split()).strip()
            if normalized and normalized.casefold() not in seen:
                subjects.append(normalized)
                seen.add(normalized.casefold())
        return subjects

    @field_validator("attendance_values")
    @classmethod
    def validate_attendance_values(cls, value: list[str]) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item).strip()
            if normalized and normalized.casefold() not in seen:
                tokens.append(normalized)
                seen.add(normalized.casefold())
        return tokens


@dataclass
class ImportStats:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, row: int, message: str) -> None:
        self.failed += 1
        self.errors.append({"row": row, "error": message})
        logger.warning("Row {} failed: {}", row, message)

    def add_skip(self, row: int, message: str) -> None:
        self.skipped += 1
        self.errors.append({"row": row, "error": message})
        logger.warning("Row {} skipped: {}", row, message)


@dataclass
class ImportContext:
    db: Session
    teacher: Any
    stats: ImportStats
    ai_response: AIStructureResponse
    header_row_index: int
    student_cache: dict[str, Any]
    subject_cache: dict[str, list[Any]]
    record_cache: dict[tuple[int, int, int], Any]
    attendance_cache: dict[tuple[int, int, date], Any]


def normalize_column_name(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d.%m.%y").lower()
    if hasattr(value, "strftime") and not isinstance(value, str):
        try:
            return value.strftime("%d.%m.%y").lower()
        except Exception:
            pass
    text = str(value).strip().lower().replace("_", " ")
    text = re.sub(r"\s+", " ", text).rstrip(":.")
    return text


def normalize_mapping_value(value: Any) -> str:
    return " ".join(str(value).strip().lower().split())


def parse_mapping_value(value: str) -> tuple[str, str | None]:
    if value in BASE_MAPPING_FIELDS:
        return value, None
    for prefix in PREFIX_MAPPINGS:
        if value.startswith(prefix):
            subject_name = value.split(":", 1)[1].strip()
            if not subject_name:
                raise ValueError(f"Mapping '{value}' must include a subject name.")
            return prefix[:-1], subject_name
    raise ValueError(f"Unsupported mapping value '{value}'.")


def is_date_column(col: Any) -> bool:
    try:
        pd.to_datetime(col, errors="raise", dayfirst=True)
        return True
    except Exception:
        return False


def parse_date_column(col: Any) -> date | None:
    try:
        return pd.to_datetime(col, errors="raise", dayfirst=True).date()
    except Exception:
        return None


def read_raw_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    buffer = io.BytesIO(content)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buffer, header=None, dtype=object)
    return pd.read_excel(buffer, header=None, dtype=object, engine="openpyxl")


def read_structured_dataframe(content: bytes, filename: str, header_row_index: int) -> pd.DataFrame:
    buffer = io.BytesIO(content)
    if filename.lower().endswith(".csv"):
        dataframe = pd.read_csv(buffer, header=header_row_index, dtype=object)
    else:
        dataframe = pd.read_excel(buffer, header=header_row_index, dtype=object, engine="openpyxl")

    dataframe = dataframe.dropna(how="all").reset_index(drop=True)
    dataframe.columns = dedupe_columns([normalize_column_name(column) for column in dataframe.columns])
    return dataframe


def dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for index, column in enumerate(columns):
        name = column or f"unnamed: {index}"
        count = seen.get(name, 0)
        deduped.append(name if count == 0 else f"{name}_{count}")
        seen[name] = count + 1
    return deduped


def build_structure_preview(raw_df: pd.DataFrame) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row_index in range(min(len(raw_df), HEADER_SCAN_LIMIT)):
        values = [serialize_preview_value(value) for value in raw_df.iloc[row_index].tolist()]
        if any(value is not None for value in values):
            preview.append({"row_index": row_index, "values": values})
        if len(preview) >= SAMPLE_ROW_LIMIT:
            break
    return preview


def serialize_preview_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def analyze_file_structure(filename: str, raw_df: pd.DataFrame) -> AIStructureResponse:
    api_key = settings.groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    request_payload = {
        "rows": build_structure_preview(raw_df),
    }

    system_prompt = (
        "You are a strict Excel structure analyzer.\n"
        "You MUST return ONLY valid JSON that matches this exact schema:\n"
        "{\n"
        '  "header_row_index": number,\n'
        '  "primary_key": string,\n'
        '  "columns": {"original_column_name": "mapped_field_name"},\n'
        '  "file_type": "marks" | "attendance" | "mixed",\n'
        '  "format": "wide" | "long" | "summary" | "daily",\n'
        '  "subjects": [],\n'
        '  "value_type": "marks" | "attendance" | "percentage",\n'
        '  "attendance_values": [],\n'
        '  "has_dates": true | false\n'
        "}\n"
        'The input format is {"rows": [...]}.\n'
        'Use the row_index values inside rows to choose header_row_index (0-based).\n'
        'The "columns" field MUST be an object, never a list.\n'
        'The "subjects" field MUST always be a list.\n'
        'The "attendance_values" field MUST always be a list.\n'
        "Never return null values.\n"
        "Never invent columns that are not visible in the detected header row.\n"
        "Detect the roll number column and return its original header name as primary_key.\n"
        "Map the primary key column to roll_number inside columns.\n"
        "Allowed mapped_field_name values are: roll_number, student_name, email, department, section, year, semester, subject, marks, attendance, percentage, cgpa, sgpa, backlogs, detained, date, ignore, subject_marks:<subject_name>, subject_attendance:<subject_name>, subject_percentage:<subject_name>.\n"
        "If columns look like dates and row values look like P/A attendance, set file_type=attendance, format=daily, value_type=attendance, and has_dates=true.\n"
        "Return ONLY valid JSON."
    )

    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(request_payload, ensure_ascii=True, default=str)},
    ]

    content = request_ai_structure_completion(filename, base_messages, api_key)
    try:
        return parse_ai_structure_response(filename, content)
    except ValueError as exc:
        logger.warning(
            "AI response for '{}' failed strict validation on first attempt; retrying once. Error: {}",
            filename,
            exc,
        )

    retry_messages = [
        *base_messages,
        {"role": "assistant", "content": content},
        {
            "role": "user",
            "content": (
                "Your previous response was invalid. Return ONLY valid JSON matching the schema exactly. "
                "Fix these rules: columns must be an object, subjects must be a list, attendance_values must be a list, "
                "primary_key must be a string, and null values are not allowed."
            ),
        },
    ]
    retry_content = request_ai_structure_completion(filename, retry_messages, api_key)
    return parse_ai_structure_response(filename, retry_content)


def request_ai_structure_completion(filename: str, messages: list[dict[str, str]], api_key: str) -> str:
    body = {
        "model": settings.groq_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Requesting AI structure analysis for '{}'.", filename)
    with httpx.Client(timeout=settings.groq_timeout_seconds) as client:
        response = client.post(settings.groq_endpoint, headers=headers, json=body)
        response.raise_for_status()

    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    logger.info("AI structure response received for '{}'.", filename)
    logger.debug("AI raw response for '{}': {}", filename, content)
    return content


def parse_ai_structure_response(filename: str, content: str) -> AIStructureResponse:
    try:
        parsed = json.loads(content)
        return AIStructureResponse.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.error("Invalid AI response for '{}': {}", filename, content)
        raise ValueError(f"Invalid AI response: {exc}") from exc


def validate_ai_response(ai_response: AIStructureResponse, raw_df: pd.DataFrame, dataframe: pd.DataFrame) -> None:
    if ai_response.header_row_index >= len(raw_df):
        raise ValueError(
            f"header_row_index {ai_response.header_row_index} is outside the file (rows={len(raw_df)})."
        )

    column_set = set(dataframe.columns)
    unknown_columns = set(ai_response.columns.keys()).difference(column_set)
    if unknown_columns:
        raise ValueError(f"AI referenced columns that do not exist: {sorted(unknown_columns)}")

    if ai_response.primary_key not in column_set:
        raise ValueError(f"AI primary_key '{ai_response.primary_key}' does not exist in the dataframe.")

    if ai_response.primary_key not in ai_response.columns:
        raise ValueError(
            f"AI primary_key '{ai_response.primary_key}' must be present in the columns mapping."
        )

    if ai_response.columns[ai_response.primary_key] != "roll_number":
        raise ValueError(
            f"AI primary_key '{ai_response.primary_key}' must map to 'roll_number', "
            f"got '{ai_response.columns[ai_response.primary_key]}'."
        )

    if not columns_for_mapping(ai_response, "roll_number"):
        raise ValueError("AI response must map at least one column to roll_number.")

    if ai_response.file_type in {FileType.MARKS, FileType.MIXED}:
        has_marks = bool(columns_for_mapping(ai_response, "marks")) or bool(columns_for_prefix(ai_response, "subject_marks"))
        if not has_marks:
            raise ValueError("Marks or mixed files must include marks mappings.")

    if ai_response.file_type in {FileType.ATTENDANCE, FileType.MIXED} and ai_response.has_dates:
        if not any(is_date_column(column) for column in dataframe.columns):
            raise ValueError("AI indicated date columns, but none were detected in the dataframe headers.")


def columns_for_mapping(ai_response: AIStructureResponse, mapping: str) -> list[str]:
    return [column for column, mapped in ai_response.columns.items() if mapped == mapping]


def columns_for_prefix(ai_response: AIStructureResponse, prefix: str) -> dict[str, str]:
    results: dict[str, str] = {}
    for column, mapped in ai_response.columns.items():
        kind, subject = parse_mapping_value(mapped)
        if kind == prefix and subject:
            results[column] = subject
    return results


def excel_row_number(index: int, header_row_index: int) -> int:
    return index + header_row_index + 2


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def normalize_roll_number(value: Any) -> str | None:
    if is_empty(value):
        return None
    return " ".join(str(value).split()).strip().upper()


def normalize_text(value: Any) -> str | None:
    if is_empty(value):
        return None
    return " ".join(str(value).split()).strip()


def parse_float(value: Any, *, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if is_empty(value):
        return None
    candidate = str(value).strip().replace("%", "").replace(",", "")
    try:
        parsed = float(candidate)
    except (TypeError, ValueError):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def parse_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    parsed = parse_float(value, minimum=minimum, maximum=maximum)
    if parsed is None:
        return None
    if float(parsed).is_integer():
        return int(parsed)
    return None


def parse_bool(value: Any) -> bool | None:
    if is_empty(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    return None


def parse_attendance_status(value: Any, attendance_values: list[str]) -> AttendanceStatus | None:
    if is_empty(value):
        return None

    normalized = str(value).strip().lower()
    token_map = {
        "p": AttendanceStatus.PRESENT,
        "present": AttendanceStatus.PRESENT,
        "a": AttendanceStatus.ABSENT,
        "absent": AttendanceStatus.ABSENT,
    }
    if len(attendance_values) >= 2:
        token_map[attendance_values[0].strip().lower()] = AttendanceStatus.PRESENT
        token_map[attendance_values[1].strip().lower()] = AttendanceStatus.ABSENT
    return token_map.get(normalized)


def resolve_attendance_subject_name(payload: dict[str, Any], ai_response: AIStructureResponse) -> str | None:
    subject_name = payload["subject"]
    if subject_name:
        return subject_name
    if len(ai_response.subjects) == 1:
        return ai_response.subjects[0]
    if ai_response.file_type == FileType.ATTENDANCE and ai_response.format == SheetFormat.DAILY:
        return ATTENDANCE_FALLBACK_SUBJECT
    return None


def resolve_subject_semester(subject_name: str | None, semester: int | None) -> int | None:
    if semester is not None:
        return semester
    if subject_name == ATTENDANCE_FALLBACK_SUBJECT:
        return ATTENDANCE_FALLBACK_SEMESTER
    return None


def get_first_value(row: pd.Series, ai_response: AIStructureResponse, mapping: str) -> Any:
    for column in columns_for_mapping(ai_response, mapping):
        if column in row.index and not is_empty(row[column]):
            return row[column]
    return None


def resolve_row_payload(row: pd.Series, ai_response: AIStructureResponse) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    roll_number = normalize_roll_number(get_first_value(row, ai_response, "roll_number"))
    if not roll_number:
        errors.append("Missing roll_number.")

    return (
        {
            "roll_number": roll_number,
            "student_name": normalize_text(get_first_value(row, ai_response, "student_name")),
            "email": normalize_text(get_first_value(row, ai_response, "email")),
            "department": normalize_text(get_first_value(row, ai_response, "department")),
            "section": normalize_text(get_first_value(row, ai_response, "section")),
            "year": parse_int(get_first_value(row, ai_response, "year"), minimum=1, maximum=4),
            "semester": parse_int(get_first_value(row, ai_response, "semester"), minimum=1, maximum=8),
            "cgpa": parse_float(get_first_value(row, ai_response, "cgpa"), minimum=0, maximum=10),
            "sgpa": parse_float(get_first_value(row, ai_response, "sgpa"), minimum=0, maximum=10),
            "backlogs": parse_int(get_first_value(row, ai_response, "backlogs"), minimum=0),
            "detained": parse_bool(get_first_value(row, ai_response, "detained")),
            "subject": normalize_text(get_first_value(row, ai_response, "subject")),
            "marks": parse_float(get_first_value(row, ai_response, "marks"), minimum=0, maximum=100),
            "attendance": parse_float(get_first_value(row, ai_response, "attendance"), minimum=0, maximum=100),
            "percentage": parse_float(get_first_value(row, ai_response, "percentage"), minimum=0, maximum=100),
            "date": get_first_value(row, ai_response, "date"),
        },
        errors,
    )


def apply_outcome(stats: ImportStats, row_number: int, outcome: str, label: str) -> None:
    if outcome == "created":
        stats.created += 1
        logger.info("Row {} {} created.", row_number, label)
    elif outcome == "updated":
        stats.updated += 1
        logger.info("Row {} {} updated.", row_number, label)
    elif outcome == "skipped":
        logger.info("Row {} {} unchanged.", row_number, label)


async def start_asynchronous_import(
    db: Session,
    current_user: User,
    filename: str,
    content: bytes,
    teacher_id: int | None = None,
) -> int:
    audit = create_import_audit(
        db,
        uploaded_by_id=current_user.id,
        filename=filename,
        status=ImportStatus.PENDING,
    )
    db.commit()
    logger.info("Initiated import for {} (audit_id={})", filename, audit.id)
    return audit.id


def process_excel_background_task(
    db_factory: Any,
    audit_id: int,
    filename: str,
    content: bytes,
    teacher_user_id: int,
    teacher_id_form: int | None = None,
) -> None:
    db: Session = db_factory()
    stats = ImportStats()
    audit: ImportAudit | None = None

    try:
        audit = db.get(ImportAudit, audit_id)
        if not audit:
            logger.error("Audit {} not found in background task.", audit_id)
            return

        user = db.get(User, teacher_user_id)
        if not user:
            logger.error("User {} not found in background task.", teacher_user_id)
            return

        audit.status = ImportStatus.PROCESSING
        db.commit()

        start_time = time.time()
        raw_df = read_raw_dataframe(content, filename)
        if raw_df.empty:
            _fail_audit(db, audit, "Uploaded file is empty.")
            return

        try:
            ai_response = analyze_file_structure(filename, raw_df)
            dataframe = read_structured_dataframe(content, filename, ai_response.header_row_index)
            validate_ai_response(ai_response, raw_df, dataframe)
        except ValueError as exc:
            logger.warning("Import {} rejected during AI structure analysis: {}", audit_id, exc)
            _fail_audit(db, audit, str(exc))
            return

        stats.total_rows = len(dataframe)
        audit.total_rows = stats.total_rows
        db.commit()

        logger.info(
            "Detected file structure for '{}': file_type={}, format={}, value_type={}, header_row_index={}",
            filename,
            ai_response.file_type.value,
            ai_response.format.value,
            ai_response.value_type.value,
            ai_response.header_row_index,
        )
        logger.info("Columns after AI-driven header handling: {}", dataframe.columns.tolist())

        teacher = resolve_teacher(db, user, teacher_id_form)
        student_cache, subject_cache, record_cache, attendance_cache = prepare_caches(db, dataframe, ai_response)
        context = ImportContext(
            db=db,
            teacher=teacher,
            stats=stats,
            ai_response=ai_response,
            header_row_index=ai_response.header_row_index,
            student_cache=student_cache,
            subject_cache=subject_cache,
            record_cache=record_cache,
            attendance_cache=attendance_cache,
        )

        if ai_response.file_type in {FileType.MARKS, FileType.MIXED}:
            process_marks(dataframe, ai_response, context)
        if ai_response.file_type in {FileType.ATTENDANCE, FileType.MIXED}:
            process_attendance(dataframe, ai_response, context)

        if time.time() - start_time > 900:
            _fail_audit(db, audit, "Processing timeout.")
            return

        audit.status = ImportStatus.COMPLETED
        audit.created = stats.created
        audit.updated = stats.updated
        audit.skipped = stats.skipped
        audit.failed = stats.failed
        audit.errors_json = json.dumps(stats.errors[:1000])
        db.commit()
        logger.info(
            "Import {} finished. created={} updated={} skipped={} failed={}",
            audit_id,
            stats.created,
            stats.updated,
            stats.skipped,
            stats.failed,
        )

    except Exception as exc:
        logger.exception("Critical failure in background task for audit {}", audit_id)
        if audit is not None:
            _fail_audit(db, audit, f"System error: {exc}")
    finally:
        db.close()


def prepare_caches(
    db: Session,
    dataframe: pd.DataFrame,
    ai_response: AIStructureResponse,
) -> tuple[dict[str, Any], dict[str, list[Any]], dict[tuple[int, int, int], Any], dict[tuple[int, int, date], Any]]:
    roll_numbers: set[str] = set()
    subject_names: set[str] = {subject for subject in ai_response.subjects if subject}

    roll_columns = columns_for_mapping(ai_response, "roll_number")
    subject_columns = columns_for_mapping(ai_response, "subject")
    subject_names.update(columns_for_prefix(ai_response, "subject_marks").values())
    subject_names.update(columns_for_prefix(ai_response, "subject_attendance").values())
    subject_names.update(columns_for_prefix(ai_response, "subject_percentage").values())

    if (
        ai_response.file_type == FileType.ATTENDANCE
        and ai_response.format == SheetFormat.DAILY
        and not subject_names
    ):
        subject_names.add(ATTENDANCE_FALLBACK_SUBJECT)
        logger.warning(
            "Attendance file does not expose a subject column or single AI subject; using fallback subject '{}'.",
            ATTENDANCE_FALLBACK_SUBJECT,
        )

    for _, row in dataframe.iterrows():
        for column in roll_columns:
            if column in row.index:
                normalized_roll = normalize_roll_number(row[column])
                if normalized_roll:
                    roll_numbers.add(normalized_roll)
        for column in subject_columns:
            if column in row.index:
                subject_name = normalize_text(row[column])
                if subject_name:
                    subject_names.add(subject_name)

    student_cache = load_student_cache_scoped(db, list(roll_numbers))
    subject_cache = load_subject_cache(db, list(subject_names))
    student_ids = [student.id for student in student_cache.values()]
    subject_ids = [subject.id for subjects in subject_cache.values() for subject in subjects]
    record_cache = load_record_cache_scoped(db, student_ids, subject_ids or None)
    attendance_cache = load_attendance_cache_scoped(db, student_ids, subject_ids or None)
    return student_cache, subject_cache, record_cache, attendance_cache


def process_marks(dataframe: pd.DataFrame, ai_response: AIStructureResponse, context: ImportContext) -> None:
    long_subject_column = next(iter(columns_for_mapping(ai_response, "subject")), None)
    long_marks_column = next(iter(columns_for_mapping(ai_response, "marks")), None)
    wide_mark_columns = columns_for_prefix(ai_response, "subject_marks")
    wide_attendance_columns = columns_for_prefix(ai_response, "subject_attendance")
    wide_percentage_columns = columns_for_prefix(ai_response, "subject_percentage")

    for row_index, row in dataframe.iterrows():
        row_number = excel_row_number(row_index, context.header_row_index)
        payload, payload_errors = resolve_row_payload(row, ai_response)
        if payload_errors:
            context.stats.add_skip(row_number, "; ".join(payload_errors))
            continue

        student, _ = get_or_create_student(
            context.db,
            context.student_cache,
            roll_number=payload["roll_number"],
            name=payload["student_name"],
            email=payload["email"],
            department=payload["department"],
            year=payload["year"],
            section=payload["section"],
            cgpa=payload["cgpa"],
            sgpa=payload["sgpa"],
            teacher_department=context.teacher.department,
        )
        ensure_teacher_link(context.db, student, context.teacher)

        if payload["semester"] is not None and any(
            value is not None for value in (payload["sgpa"], payload["cgpa"], payload["backlogs"])
        ):
            upsert_semester_result(
                context.db,
                student_id=student.id,
                semester=payload["semester"],
                sgpa=payload["sgpa"],
                cgpa=payload["cgpa"],
                backlogs=payload["backlogs"],
            )

        row_had_operation = False

        if long_subject_column and long_marks_column:
            row_had_operation = process_long_marks_row(row_number, row, payload, student, ai_response, context) or row_had_operation

        if wide_mark_columns:
            row_had_operation = process_wide_marks_row(
                row_number,
                row,
                payload,
                student,
                wide_mark_columns,
                wide_attendance_columns,
                wide_percentage_columns,
                context,
            ) or row_had_operation

        if not row_had_operation and (long_subject_column or wide_mark_columns):
            logger.info("Row {} had no valid marks records to write.", row_number)


def process_long_marks_row(
    row_number: int,
    row: pd.Series,
    payload: dict[str, Any],
    student: Any,
    ai_response: AIStructureResponse,
    context: ImportContext,
) -> bool:
    subject_name = payload["subject"]
    if not subject_name:
        context.stats.add_skip(row_number, "Marks row skipped: subject is missing.")
        return False
    if payload["marks"] is None:
        context.stats.add_skip(row_number, "Marks row skipped: marks value is missing or invalid.")
        return False

    try:
        subject = get_or_create_subject(
            context.db,
            context.subject_cache,
            name=subject_name,
            semester=payload["semester"],
        )
        ensure_student_subject_link(context.db, student, subject)

        attendance_percentage = payload["percentage"]
        if attendance_percentage is None:
            attendance_percentage = payload["attendance"]

        outcome = upsert_academic_record(
            context.db,
            context.record_cache,
            student_id=student.id,
            subject_id=subject.id,
            semester=subject.semester,
            marks=payload["marks"],
            attendance_percentage=attendance_percentage,
            backlogs=payload["backlogs"],
            detained=payload["detained"],
        )
        apply_outcome(context.stats, row_number, outcome, f"marks record for {subject.name}")
        return outcome != "skipped"
    except Exception as exc:
        context.stats.add_error(row_number, str(exc))
        return False


def process_wide_marks_row(
    row_number: int,
    row: pd.Series,
    payload: dict[str, Any],
    student: Any,
    wide_mark_columns: dict[str, str],
    wide_attendance_columns: dict[str, str],
    wide_percentage_columns: dict[str, str],
    context: ImportContext,
) -> bool:
    wrote = False

    for column_name, subject_name in wide_mark_columns.items():
        cell_value = row.get(column_name)
        if is_empty(cell_value):
            continue

        marks = parse_float(cell_value, minimum=0, maximum=100)
        if marks is None:
            context.stats.add_error(row_number, f"Invalid marks value '{cell_value}' for subject '{subject_name}'.")
            continue

        attendance_percentage = None
        for attendance_column, mapped_subject in wide_percentage_columns.items():
            if mapped_subject.casefold() == subject_name.casefold():
                attendance_percentage = parse_float(row.get(attendance_column), minimum=0, maximum=100)
                break
        if attendance_percentage is None:
            for attendance_column, mapped_subject in wide_attendance_columns.items():
                if mapped_subject.casefold() == subject_name.casefold():
                    attendance_percentage = parse_float(row.get(attendance_column), minimum=0, maximum=100)
                    break

        try:
            subject = get_or_create_subject(
                context.db,
                context.subject_cache,
                name=subject_name,
                semester=payload["semester"],
            )
            ensure_student_subject_link(context.db, student, subject)
            outcome = upsert_academic_record(
                context.db,
                context.record_cache,
                student_id=student.id,
                subject_id=subject.id,
                semester=subject.semester,
                marks=marks,
                attendance_percentage=attendance_percentage,
                backlogs=payload["backlogs"],
                detained=payload["detained"],
            )
            apply_outcome(context.stats, row_number, outcome, f"marks record for {subject.name}")
            wrote = wrote or outcome != "skipped"
        except Exception as exc:
            context.stats.add_error(row_number, str(exc))

    return wrote


def process_attendance(dataframe: pd.DataFrame, ai_response: AIStructureResponse, context: ImportContext) -> None:
    date_columns = [column for column in dataframe.columns if is_date_column(column)]
    long_date_column = next(iter(columns_for_mapping(ai_response, "date")), None)
    long_attendance_column = next(iter(columns_for_mapping(ai_response, "attendance")), None)
    long_percentage_column = next(iter(columns_for_mapping(ai_response, "percentage")), None)

    if ai_response.file_type == FileType.MIXED and not date_columns and not long_date_column:
        logger.info("Mixed file has no explicit attendance dates; attendance summary is handled by marks processing.")
        return

    for row_index, row in dataframe.iterrows():
        row_number = excel_row_number(row_index, context.header_row_index)
        payload, payload_errors = resolve_row_payload(row, ai_response)
        if payload_errors:
            context.stats.add_skip(row_number, "; ".join(payload_errors))
            continue

        student, _ = get_or_create_student(
            context.db,
            context.student_cache,
            roll_number=payload["roll_number"],
            name=payload["student_name"],
            email=payload["email"],
            department=payload["department"],
            year=payload["year"],
            section=payload["section"],
            cgpa=payload["cgpa"],
            sgpa=payload["sgpa"],
            teacher_department=context.teacher.department,
        )
        ensure_teacher_link(context.db, student, context.teacher)

        subject_name = resolve_attendance_subject_name(payload, ai_response)
        subject_semester = resolve_subject_semester(subject_name, payload["semester"])

        if date_columns:
            process_daily_attendance_row(
                row_number=row_number,
                row=row,
                payload=payload,
                student=student,
                subject_name=subject_name,
                subject_semester=subject_semester,
                date_columns=date_columns,
                ai_response=ai_response,
                context=context,
            )

        if long_date_column and long_attendance_column:
            process_long_attendance_row(
                row_number=row_number,
                row=row,
                payload=payload,
                student=student,
                subject_name=subject_name,
                subject_semester=subject_semester,
                long_date_column=long_date_column,
                long_attendance_column=long_attendance_column,
                ai_response=ai_response,
                context=context,
            )

        if ai_response.file_type == FileType.ATTENDANCE and not date_columns and long_percentage_column:
            process_summary_attendance_row(
                row_number=row_number,
                row=row,
                payload=payload,
                student=student,
                subject_name=subject_name,
                subject_semester=subject_semester,
                percentage_column=long_percentage_column,
                context=context,
            )


def process_daily_attendance_row(
    *,
    row_number: int,
    row: pd.Series,
    payload: dict[str, Any],
    student: Any,
    subject_name: str | None,
    subject_semester: int | None,
    date_columns: list[str],
    ai_response: AIStructureResponse,
    context: ImportContext,
) -> None:
    if not subject_name:
        context.stats.add_skip(row_number, "Attendance row skipped: subject is missing and AI did not provide one.")
        return

    try:
        subject = get_or_create_subject(
            context.db,
            context.subject_cache,
            name=subject_name,
            semester=subject_semester,
        )
        ensure_student_subject_link(context.db, student, subject)

        wrote_attendance = False
        for column_name in date_columns:
            attendance_date = parse_date_column(column_name)
            if attendance_date is None:
                continue

            status = parse_attendance_status(row.get(column_name), ai_response.attendance_values)
            if status is None:
                if not is_empty(row.get(column_name)):
                    logger.warning(
                        "Row {} date column '{}' has unsupported attendance token '{}'.",
                        row_number,
                        column_name,
                        row.get(column_name),
                    )
                continue

            outcome = upsert_attendance_record(
                context.db,
                context.attendance_cache,
                student_id=student.id,
                subject_id=subject.id,
                attendance_date=attendance_date,
                status=status,
            )
            apply_outcome(context.stats, row_number, outcome, f"attendance record {subject.name} {attendance_date}")
            wrote_attendance = wrote_attendance or outcome != "skipped"

        if wrote_attendance:
            percentage = calculate_attendance_percentage(
                context.db,
                student_id=student.id,
                subject_id=subject.id,
            )
            if percentage is not None:
                outcome = upsert_academic_record(
                    context.db,
                    context.record_cache,
                    student_id=student.id,
                    subject_id=subject.id,
                    semester=subject.semester,
                    attendance_percentage=percentage,
                )
                apply_outcome(context.stats, row_number, outcome, f"attendance summary for {subject.name}")
    except Exception as exc:
        context.stats.add_error(row_number, str(exc))


def process_long_attendance_row(
    *,
    row_number: int,
    row: pd.Series,
    payload: dict[str, Any],
    student: Any,
    subject_name: str | None,
    subject_semester: int | None,
    long_date_column: str,
    long_attendance_column: str,
    ai_response: AIStructureResponse,
    context: ImportContext,
) -> None:
    if not subject_name:
        context.stats.add_skip(row_number, "Attendance row skipped: subject is missing.")
        return

    attendance_date = parse_date_column(row.get(long_date_column))
    if attendance_date is None:
        context.stats.add_error(row_number, f"Invalid attendance date '{row.get(long_date_column)}'.")
        return

    status = parse_attendance_status(row.get(long_attendance_column), ai_response.attendance_values)
    if status is None:
        context.stats.add_skip(row_number, f"Invalid attendance token '{row.get(long_attendance_column)}'.")
        return

    try:
        subject = get_or_create_subject(
            context.db,
            context.subject_cache,
            name=subject_name,
            semester=subject_semester,
        )
        ensure_student_subject_link(context.db, student, subject)
        outcome = upsert_attendance_record(
            context.db,
            context.attendance_cache,
            student_id=student.id,
            subject_id=subject.id,
            attendance_date=attendance_date,
            status=status,
        )
        apply_outcome(context.stats, row_number, outcome, f"attendance record for {subject.name}")
    except Exception as exc:
        context.stats.add_error(row_number, str(exc))


def process_summary_attendance_row(
    *,
    row_number: int,
    row: pd.Series,
    payload: dict[str, Any],
    student: Any,
    subject_name: str | None,
    subject_semester: int | None,
    percentage_column: str,
    context: ImportContext,
) -> None:
    if not subject_name:
        context.stats.add_skip(row_number, "Attendance summary row skipped: subject is missing.")
        return

    percentage = parse_float(row.get(percentage_column), minimum=0, maximum=100)
    if percentage is None:
        context.stats.add_skip(row_number, f"Invalid attendance percentage '{row.get(percentage_column)}'.")
        return

    try:
        subject = get_or_create_subject(
            context.db,
            context.subject_cache,
            name=subject_name,
            semester=subject_semester,
        )
        ensure_student_subject_link(context.db, student, subject)
        outcome = upsert_academic_record(
            context.db,
            context.record_cache,
            student_id=student.id,
            subject_id=subject.id,
            semester=subject.semester,
            attendance_percentage=percentage,
        )
        if outcome == "skipped":
            context.stats.add_skip(
                row_number,
                f"Attendance percentage for subject '{subject.name}' skipped because no marks record exists yet.",
            )
        else:
            apply_outcome(context.stats, row_number, outcome, f"attendance summary for {subject.name}")
    except Exception as exc:
        context.stats.add_error(row_number, str(exc))


def _fail_audit(db: Session, audit: ImportAudit, message: str) -> None:
    try:
        audit.status = ImportStatus.FAILED
        errors = json.loads(audit.errors_json) if audit.errors_json else []
        errors.append({"row": 0, "error": message})
        audit.errors_json = json.dumps(errors[:1000])
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Could not update audit {} status to FAILED.", audit.id)
