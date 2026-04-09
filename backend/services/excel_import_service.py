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


def is_date_column(column: Any) -> bool:
    try:
        pd.to_datetime(column, errors="raise", dayfirst=True)
        return True
    except Exception:
        return False


def parse_date_column(column: Any) -> date | None:
    try:
        return pd.to_datetime(column, errors="raise", dayfirst=True).date()
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


def coerce_non_negative_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_subject_name(value: Any) -> str:
    return " ".join(str(value).split()).strip()


def extract_header_candidates(raw_df: pd.DataFrame, header_row_index: int) -> list[str]:
    if raw_df.empty:
        return []
    safe_index = min(max(header_row_index, 0), len(raw_df) - 1)
    raw_headers = raw_df.iloc[safe_index].tolist()
    return dedupe_columns([normalize_column_name(column) for column in raw_headers])


def infer_mapping_from_column_name(column_name: str, *, file_type: str, has_dates: bool) -> str:
    normalized = normalize_column_name(column_name)
    compact = normalized.replace(" ", "")
    if not normalized:
        return "ignore"
    if is_date_column(normalized):
        return "ignore"
    if "roll" in normalized and ("no" in normalized or "number" in normalized):
        return "roll_number"
    if normalized in {"name", "student name", "student"}:
        return "student_name"
    if "email" in normalized:
        return "email"
    if "department" in normalized or normalized == "dept":
        return "department"
    if "section" in normalized:
        return "section"
    if normalized == "year":
        return "year"
    if normalized in {"semester", "sem"}:
        return "semester"
    if normalized in {"subject", "subject name", "course", "course name"}:
        return "subject"
    if normalized in {"marks", "mark", "score", "total", "grade"}:
        return "marks"
    if "attendance" in normalized and "%" in normalized:
        return "percentage"
    if "attendance" in normalized or normalized in {"status", "present absent"}:
        return "attendance"
    if "percentage" in normalized or compact in {"attendance%", "attendancepercentage"}:
        return "percentage"
    if normalized == "cgpa":
        return "cgpa"
    if normalized == "sgpa":
        return "sgpa"
    if "backlog" in normalized:
        return "backlogs"
    if "detain" in normalized:
        return "detained"
    if file_type == FileType.ATTENDANCE.value and has_dates:
        return "ignore"
    return "ignore"


def normalize_mapping_target(
    target: Any,
    *,
    source_column: str,
    file_type: str,
    has_dates: bool,
) -> str:
    if target is None:
        return infer_mapping_from_column_name(source_column, file_type=file_type, has_dates=has_dates)

    normalized = normalize_mapping_value(target)
    if not normalized:
        return infer_mapping_from_column_name(source_column, file_type=file_type, has_dates=has_dates)

    aliases = {
        "roll no": "roll_number",
        "roll number": "roll_number",
        "rollnumber": "roll_number",
        "student roll number": "roll_number",
        "student name": "student_name",
        "name": "student_name",
        "full name": "student_name",
        "mail": "email",
        "e-mail": "email",
        "dept": "department",
        "branch": "department",
        "sem": "semester",
        "subject name": "subject",
        "course": "subject",
        "course name": "subject",
        "mark": "marks",
        "score": "marks",
        "numeric": "marks",
        "status": "attendance",
        "present/absent": "attendance",
        "attendance status": "attendance",
        "attendance percentage": "percentage",
        "percent": "percentage",
        "cgpa score": "cgpa",
        "sgpa score": "sgpa",
        "backlog": "backlogs",
    }
    normalized = aliases.get(normalized, normalized)

    if normalized.startswith("subject:"):
        subject_name = normalize_subject_name(normalized.split(":", 1)[1]).lower()
        return f"subject_marks:{subject_name}" if subject_name else "ignore"

    for prefix in PREFIX_MAPPINGS:
        if normalized.startswith(prefix):
            subject_name = normalize_subject_name(normalized.split(":", 1)[1]).lower()
            return f"{prefix}{subject_name}" if subject_name else "ignore"

    if normalized.startswith("date:") or is_date_column(normalized):
        return "ignore"

    try:
        parse_mapping_value(normalized)
        return normalized
    except ValueError:
        return infer_mapping_from_column_name(source_column, file_type=file_type, has_dates=has_dates)


def normalize_columns_mapping(
    raw_columns: Any,
    *,
    header_candidates: list[str],
    file_type: str,
    has_dates: bool,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if isinstance(raw_columns, dict):
        items = raw_columns.items()
    elif isinstance(raw_columns, list):
        items = zip(header_candidates, raw_columns)
    else:
        items = []

    for raw_source, raw_target in items:
        source = normalize_column_name(raw_source)
        if not source:
            continue
        normalized[source] = normalize_mapping_target(
            raw_target,
            source_column=source,
            file_type=file_type,
            has_dates=has_dates,
        )
    if not normalized:
        for source in header_candidates:
            normalized[source] = infer_mapping_from_column_name(source, file_type=file_type, has_dates=has_dates)
    return normalized


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        iterable = value.values()
    elif isinstance(value, list):
        iterable = value
    else:
        iterable = [value]

    normalized_items: list[str] = []
    seen: set[str] = set()
    for item in iterable:
        text = normalize_subject_name(item)
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        normalized_items.append(text)
        seen.add(lowered)
    return normalized_items


def normalize_file_type(value: Any, *, columns: dict[str, str], has_dates: bool) -> str:
    normalized = normalize_mapping_value(value or "")
    aliases = {
        "student_report": FileType.MIXED.value,
        "report": FileType.MIXED.value,
        "mark": FileType.MARKS.value,
        "score": FileType.MARKS.value,
        "daily_attendance": FileType.ATTENDANCE.value,
    }
    normalized = aliases.get(normalized, normalized)
    has_marks = any(mapped == "marks" or mapped.startswith("subject_marks:") for mapped in columns.values())
    has_attendance = any(mapped == "attendance" or mapped.startswith("subject_attendance:") for mapped in columns.values())
    has_percentage = any(mapped == "percentage" or mapped.startswith("subject_percentage:") for mapped in columns.values())

    if has_dates or has_attendance:
        if has_marks or has_percentage:
            return FileType.MIXED.value
        return FileType.ATTENDANCE.value
    if has_marks and (has_attendance or has_percentage):
        return FileType.MIXED.value
    if has_marks:
        return FileType.MARKS.value
    if has_percentage:
        return FileType.ATTENDANCE.value
    if normalized in {item.value for item in FileType}:
        return normalized
    return FileType.MARKS.value


def normalize_sheet_format(value: Any, *, file_type: str, has_dates: bool, columns: dict[str, str]) -> str:
    normalized = normalize_mapping_value(value or "")
    aliases = {
        "table": SheetFormat.WIDE.value,
        "tabular": SheetFormat.WIDE.value,
        "sheet": SheetFormat.WIDE.value,
    }
    normalized = aliases.get(normalized, normalized)
    if has_dates:
        return SheetFormat.DAILY.value
    if any(mapped.startswith("subject_marks:") for mapped in columns.values()):
        return SheetFormat.WIDE.value
    if "subject" in columns.values():
        return SheetFormat.LONG.value
    if file_type == FileType.ATTENDANCE.value and any(
        mapped == "percentage" or mapped.startswith("subject_percentage:") for mapped in columns.values()
    ):
        return SheetFormat.SUMMARY.value
    if normalized in {item.value for item in SheetFormat}:
        return normalized
    return SheetFormat.WIDE.value


def normalize_value_type(value: Any, *, file_type: str, has_dates: bool, columns: dict[str, str]) -> str:
    normalized = normalize_mapping_value(value or "")
    if normalized == "numeric":
        normalized = ""

    aliases = {
        "score": ValueType.MARKS.value,
        "mark": ValueType.MARKS.value,
        "present_absent": ValueType.ATTENDANCE.value,
        "status": ValueType.ATTENDANCE.value,
        "percent": ValueType.PERCENTAGE.value,
    }
    normalized = aliases.get(normalized, normalized)
    has_marks = any(mapped == "marks" or mapped.startswith("subject_marks:") for mapped in columns.values())
    has_percentage = any(mapped == "percentage" or mapped.startswith("subject_percentage:") for mapped in columns.values())
    has_attendance = any(mapped == "attendance" or mapped.startswith("subject_attendance:") for mapped in columns.values())

    if file_type == FileType.ATTENDANCE.value and (has_dates or has_attendance):
        return ValueType.ATTENDANCE.value
    if has_percentage and not has_marks:
        return ValueType.PERCENTAGE.value
    if has_marks:
        return ValueType.MARKS.value
    if normalized in {item.value for item in ValueType}:
        return normalized
    return ValueType.MARKS.value


def infer_primary_key(raw_value: Any, columns: dict[str, str], header_candidates: list[str]) -> str:
    normalized = normalize_column_name(raw_value)
    if normalized and normalized in columns:
        return normalized
    for column, mapped in columns.items():
        if mapped == "roll_number":
            return column
    for header in header_candidates:
        if "roll" in header and ("no" in header or "number" in header):
            return header
    return ""


def sanitize_ai_structure_payload(filename: str, raw_payload: Any, raw_df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        raise ValueError("AI response must be a JSON object.")

    header_row_index = coerce_non_negative_int(raw_payload.get("header_row_index"), default=0)
    header_candidates = extract_header_candidates(raw_df, header_row_index)
    detected_has_dates = any(is_date_column(column) for column in header_candidates)
    provisional_has_dates = coerce_bool(
        raw_payload.get("has_dates"),
        default=detected_has_dates,
    )
    provisional_has_dates = provisional_has_dates or detected_has_dates

    provisional_file_type_value = normalize_mapping_value(raw_payload.get("file_type") or "")
    provisional_file_type = {
        "student_report": FileType.MIXED.value,
    }.get(provisional_file_type_value, provisional_file_type_value or FileType.MARKS.value)

    columns = normalize_columns_mapping(
        raw_payload.get("columns"),
        header_candidates=header_candidates,
        file_type=provisional_file_type,
        has_dates=provisional_has_dates,
    )
    file_type = normalize_file_type(raw_payload.get("file_type"), columns=columns, has_dates=provisional_has_dates)
    sheet_format = normalize_sheet_format(
        raw_payload.get("format"),
        file_type=file_type,
        has_dates=provisional_has_dates,
        columns=columns,
    )
    value_type = normalize_value_type(
        raw_payload.get("value_type"),
        file_type=file_type,
        has_dates=provisional_has_dates,
        columns=columns,
    )
    subjects = normalize_string_list(raw_payload.get("subjects"))
    attendance_values = [str(item) for item in normalize_string_list(raw_payload.get("attendance_values"))]

    for mapped in columns.values():
        for prefix in PREFIX_MAPPINGS:
            if mapped.startswith(prefix):
                subject_name = normalize_subject_name(mapped.split(":", 1)[1])
                if subject_name:
                    subjects.append(subject_name)

    deduped_subjects: list[str] = []
    seen_subjects: set[str] = set()
    for subject in subjects:
        lowered = subject.casefold()
        if lowered in seen_subjects:
            continue
        deduped_subjects.append(subject)
        seen_subjects.add(lowered)

    if file_type == FileType.ATTENDANCE.value and not attendance_values:
        attendance_values = ["P", "A"]

    sanitized = {
        "header_row_index": header_row_index,
        "primary_key": infer_primary_key(raw_payload.get("primary_key"), columns, header_candidates),
        "columns": columns,
        "file_type": file_type,
        "format": sheet_format,
        "subjects": deduped_subjects,
        "value_type": value_type,
        "attendance_values": attendance_values,
        "has_dates": provisional_has_dates,
    }
    logger.info("Sanitized AI structure response for '{}': {}", filename, sanitized)
    return sanitized


def analyze_file_structure(filename: str, raw_df: pd.DataFrame) -> AIStructureResponse:
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not configured.")

    request_payload = {"rows": build_structure_preview(raw_df)}
    system_prompt = (
        "You are a strict Excel structure analyzer.\n"
        "Return ONLY valid JSON with header_row_index, primary_key, columns, file_type, format, "
        "subjects, value_type, attendance_values, has_dates.\n"
        "columns must be an object. subjects and attendance_values must be lists. No null values.\n"
        "Map the detected primary key column to roll_number.\n"
        "Allowed mapped values: roll_number, student_name, email, department, section, year, semester, "
        "subject, marks, attendance, percentage, cgpa, sgpa, backlogs, detained, date, ignore, "
        "subject_marks:<subject_name>, subject_attendance:<subject_name>, subject_percentage:<subject_name>."
    )
    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(request_payload, ensure_ascii=True, default=str)},
    ]

    content = request_ai_structure_completion(filename, base_messages)
    try:
        return parse_ai_structure_response(filename, content, raw_df)
    except ValueError as exc:
        logger.warning("AI response for '{}' failed strict validation; retrying once: {}", filename, exc)

    retry_messages = [
        *base_messages,
        {"role": "assistant", "content": content},
        {
            "role": "user",
            "content": (
                "Your previous response was invalid. Return ONLY valid JSON. "
                "columns must be an object, subjects must be a list, attendance_values must be a list, "
                "primary_key must be a string, and null values are not allowed."
            ),
        },
    ]
    return parse_ai_structure_response(
        filename,
        request_ai_structure_completion(filename, retry_messages),
        raw_df,
    )


def request_ai_structure_completion(filename: str, messages: list[dict[str, str]]) -> str:
    body = {
        "model": settings.groq_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
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


def parse_ai_structure_response(filename: str, content: str, raw_df: pd.DataFrame) -> AIStructureResponse:
    try:
        raw_payload = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("Invalid AI JSON for '{}': {}", filename, content)
        raise ValueError(f"Invalid AI response: {exc}") from exc

    try:
        sanitized_payload = sanitize_ai_structure_payload(filename, raw_payload, raw_df)
        return AIStructureResponse.model_validate(sanitized_payload)
    except (ValidationError, ValueError) as exc:
        logger.error("Invalid AI response for '{}': {}", filename, content)
        raise ValueError(f"Invalid AI response: {exc}") from exc


def validate_ai_response(ai_response: AIStructureResponse, raw_df: pd.DataFrame, dataframe: pd.DataFrame) -> None:
    if ai_response.header_row_index >= len(raw_df):
        raise ValueError(f"header_row_index {ai_response.header_row_index} is outside the file.")
    column_set = set(dataframe.columns)
    unknown_columns = set(ai_response.columns.keys()).difference(column_set)
    if unknown_columns:
        raise ValueError(f"AI referenced columns that do not exist: {sorted(unknown_columns)}")
    if ai_response.primary_key not in column_set:
        raise ValueError(f"AI primary_key '{ai_response.primary_key}' does not exist in the dataframe.")
    if ai_response.primary_key not in ai_response.columns:
        raise ValueError(f"AI primary_key '{ai_response.primary_key}' must be present in the columns mapping.")
    if ai_response.columns[ai_response.primary_key] != "roll_number":
        raise ValueError(
            f"AI primary_key '{ai_response.primary_key}' must map to 'roll_number', "
            f"got '{ai_response.columns[ai_response.primary_key]}'."
        )
    if not columns_for_mapping(ai_response, "roll_number"):
        raise ValueError("AI response must map at least one column to roll_number.")
    if ai_response.file_type in {FileType.MARKS, FileType.MIXED}:
        if not columns_for_mapping(ai_response, "marks") and not columns_for_prefix(ai_response, "subject_marks"):
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
    return int(parsed) if float(parsed).is_integer() else None


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
    if payload["subject"]:
        return payload["subject"]
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
            "semester": parse_int(get_first_value(row, ai_response, "semester"), minimum=0, maximum=8),
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
    del content, teacher_id
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
            _fail_audit(db, audit, f"User {teacher_user_id} not found.")
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
    if ai_response.file_type == FileType.ATTENDANCE and ai_response.format == SheetFormat.DAILY and not subject_names:
        subject_names.add(ATTENDANCE_FALLBACK_SUBJECT)
        logger.warning("Attendance file missing subject context; using '{}'.", ATTENDANCE_FALLBACK_SUBJECT)
    for _, row in dataframe.iterrows():
        for column in roll_columns:
            normalized_roll = normalize_roll_number(row.get(column))
            if normalized_roll:
                roll_numbers.add(normalized_roll)
        for column in subject_columns:
            subject_name = normalize_text(row.get(column))
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
            row_had_operation = process_long_marks_row(row_number, payload, student, context) or row_had_operation
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
    payload: dict[str, Any],
    student: Any,
    context: ImportContext,
) -> bool:
    if not payload["subject"]:
        context.stats.add_skip(row_number, "Marks row skipped: subject is missing.")
        return False
    if payload["marks"] is None:
        context.stats.add_skip(row_number, "Marks row skipped: marks value is missing or invalid.")
        return False
    try:
        subject = get_or_create_subject(
            context.db,
            context.subject_cache,
            name=payload["subject"],
            semester=payload["semester"],
        )
        ensure_student_subject_link(context.db, student, subject)
        attendance_percentage = payload["percentage"] if payload["percentage"] is not None else payload["attendance"]
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
        for percentage_column, mapped_subject in wide_percentage_columns.items():
            if mapped_subject.casefold() == subject_name.casefold():
                attendance_percentage = parse_float(row.get(percentage_column), minimum=0, maximum=100)
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
            process_daily_attendance_row(row_number, row, student, subject_name, subject_semester, date_columns, ai_response, context)
        if long_date_column and long_attendance_column:
            process_long_attendance_row(
                row_number,
                row,
                student,
                subject_name,
                subject_semester,
                long_date_column,
                long_attendance_column,
                ai_response,
                context,
            )
        if ai_response.file_type == FileType.ATTENDANCE and not date_columns and long_percentage_column:
            process_summary_attendance_row(
                row_number, row, student, subject_name, subject_semester, long_percentage_column, context
            )


def process_daily_attendance_row(
    row_number: int,
    row: pd.Series,
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
        subject = get_or_create_subject(context.db, context.subject_cache, name=subject_name, semester=subject_semester)
        ensure_student_subject_link(context.db, student, subject)
        wrote_attendance = False
        for column_name in date_columns:
            attendance_date = parse_date_column(column_name)
            if attendance_date is None:
                continue
            status = parse_attendance_status(row.get(column_name), ai_response.attendance_values)
            if status is None:
                if not is_empty(row.get(column_name)):
                    logger.warning("Row {} date column '{}' has unsupported token '{}'.", row_number, column_name, row.get(column_name))
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
            percentage = calculate_attendance_percentage(context.db, student_id=student.id, subject_id=subject.id)
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
    row_number: int,
    row: pd.Series,
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
        subject = get_or_create_subject(context.db, context.subject_cache, name=subject_name, semester=subject_semester)
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
    row_number: int,
    row: pd.Series,
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
        subject = get_or_create_subject(context.db, context.subject_cache, name=subject_name, semester=subject_semester)
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
