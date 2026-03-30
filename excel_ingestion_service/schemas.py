from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileType(str, Enum):
    MARKS = "marks"
    ATTENDANCE = "attendance"
    MIXED = "mixed"


class SheetFormat(str, Enum):
    WIDE = "wide"
    LONG = "long"
    SUMMARY = "summary"
    DAILY = "daily"


class ValueType(str, Enum):
    MARKS = "marks"
    ATTENDANCE = "attendance"
    PERCENTAGE = "percentage"


class ImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


BASE_MAPPING_FIELDS = frozenset(
    {
        "roll_number",
        "name",
        "subject",
        "marks",
        "attendance",
        "percentage",
        "date",
        "ignore",
    }
)

SUBJECT_MAPPING_PREFIXES = (
    "subject_marks:",
    "subject_attendance:",
    "subject_percentage:",
)


@dataclass(frozen=True, slots=True)
class ParsedColumnMapping:
    kind: str
    subject: str | None = None


def parse_column_mapping(token: str) -> ParsedColumnMapping:
    normalized = token.strip()
    if normalized in BASE_MAPPING_FIELDS:
        return ParsedColumnMapping(kind=normalized)

    for prefix in SUBJECT_MAPPING_PREFIXES:
        if normalized.startswith(prefix):
            subject = normalized.split(":", 1)[1].strip()
            if not subject:
                raise ValueError(f"Mapping token '{token}' must include a subject name.")
            return ParsedColumnMapping(kind=prefix[:-1], subject=subject)

    raise ValueError(f"Unsupported mapping token '{token}'.")


class AIAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_type: FileType
    format: SheetFormat
    primary_key: str = Field(min_length=1)
    columns: dict[str, str] = Field(min_length=1)
    subjects: list[str] = Field(default_factory=list)
    value_type: ValueType
    attendance_values: list[str] = Field(default_factory=list)
    has_dates: bool

    @field_validator("primary_key")
    @classmethod
    def validate_primary_key(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("primary_key cannot be empty.")
        return normalized

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, mapped_value in value.items():
            normalized_key = " ".join(str(key).split()).strip()
            normalized_value = " ".join(str(mapped_value).split()).strip()
            if not normalized_key or not normalized_value:
                raise ValueError("Column mappings must have non-empty keys and values.")
            parse_column_mapping(normalized_value)
            cleaned[normalized_key] = normalized_value
        return cleaned

    @field_validator("subjects")
    @classmethod
    def validate_subjects(cls, value: list[str]) -> list[str]:
        normalized_subjects: list[str] = []
        seen: set[str] = set()
        for subject in value:
            cleaned = " ".join(str(subject).split()).strip()
            if cleaned and cleaned.casefold() not in seen:
                normalized_subjects.append(cleaned)
                seen.add(cleaned.casefold())
        return normalized_subjects

    @field_validator("attendance_values")
    @classmethod
    def validate_attendance_values(cls, value: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = str(item).strip()
            if cleaned and cleaned.casefold() not in seen:
                normalized_values.append(cleaned)
                seen.add(cleaned.casefold())
        return normalized_values


class RowError(BaseModel):
    sheet: str
    row: int
    error: str


class SheetImportReport(BaseModel):
    sheet_name: str
    file_type: FileType
    format: SheetFormat
    processed_rows: int = 0
    failed_rows: int = 0
    errors: list[RowError] = Field(default_factory=list)


class ImportReport(BaseModel):
    status: ImportStatus
    processed_rows: int
    failed_rows: int
    errors: list[RowError] = Field(default_factory=list)
    sheets: list[SheetImportReport] = Field(default_factory=list)
