from __future__ import annotations

import asyncio
import io
import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import settings
from models import Attendance, AttendanceStatus, Mark, Student, Subject
from schemas import AIAnalysisResponse, ImportReport, ImportStatus, ParsedColumnMapping, RowError, SheetImportReport, parse_column_mapping
from services.ai_service import GroqAIService


logger = logging.getLogger(__name__)


ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}


@dataclass(slots=True)
class SheetBundle:
    sheet_name: str
    dataframe: pd.DataFrame
    analysis: AIAnalysisResponse


@dataclass(slots=True)
class StudentDraft:
    roll_number: str
    name: str | None = None


@dataclass(slots=True)
class MarkDraft:
    roll_number: str
    subject_key: str
    subject_name: str
    marks: float


@dataclass(slots=True)
class AttendanceDraft:
    roll_number: str
    subject_key: str
    subject_name: str
    date_value: date | None
    status: AttendanceStatus | None
    percentage: float | None


@dataclass(slots=True)
class StagedWorkbook:
    students: dict[str, StudentDraft] = field(default_factory=dict)
    subjects: dict[str, str] = field(default_factory=dict)
    marks: dict[tuple[str, str], MarkDraft] = field(default_factory=dict)
    attendance: dict[tuple[str, str, date | None], AttendanceDraft] = field(default_factory=dict)


class ImportService:
    def __init__(self, db: Session, ai_service: GroqAIService | None = None) -> None:
        self.db = db
        self.ai_service = ai_service or GroqAIService()

    async def import_excel(self, upload_file: UploadFile) -> ImportReport:
        self._validate_file_name(upload_file.filename)
        logger.info("Excel upload started for file '%s'.", upload_file.filename)

        workbook_sheets = await self._read_workbook(upload_file)
        analyses = await asyncio.gather(
            *(self.ai_service.analyze_sheet(sheet_name, dataframe) for sheet_name, dataframe in workbook_sheets),
        )
        bundles = [
            SheetBundle(sheet_name=sheet_name, dataframe=dataframe, analysis=analysis)
            for (sheet_name, dataframe), analysis in zip(workbook_sheets, analyses, strict=True)
        ]

        report, staged_data = self._stage_workbook(bundles)
        if report.processed_rows == 0:
            report.status = ImportStatus.FAILED
            logger.warning("Excel upload failed for file '%s'; no valid rows were staged.", upload_file.filename)
            return report

        try:
            self._persist_staged_data(staged_data)
        except SQLAlchemyError as exc:
            logger.exception("Database error while importing file '%s': %s", upload_file.filename, exc)
            raise HTTPException(status_code=500, detail="Database error occurred during import.") from exc

        report.status = self._determine_report_status(report)
        logger.info(
            "Excel upload finished for file '%s' with status '%s'. Processed rows=%s failed rows=%s.",
            upload_file.filename,
            report.status.value,
            report.processed_rows,
            report.failed_rows,
        )
        return report

    async def _read_workbook(self, upload_file: UploadFile) -> list[tuple[str, pd.DataFrame]]:
        contents = await upload_file.read()
        await upload_file.close()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        try:
            excel_file = pd.ExcelFile(io.BytesIO(contents))
        except ValueError as exc:
            logger.exception("Failed to open workbook '%s': %s", upload_file.filename, exc)
            raise HTTPException(status_code=400, detail="Unable to read the uploaded Excel file.") from exc

        sheets: list[tuple[str, pd.DataFrame]] = []
        for sheet_name in excel_file.sheet_names:
            dataframe = excel_file.parse(sheet_name=sheet_name, dtype=object)
            if dataframe.shape[1] == 0:
                raise HTTPException(status_code=400, detail=f"Sheet '{sheet_name}' does not contain any columns.")
            normalized_dataframe = self._normalize_dataframe_columns(sheet_name=sheet_name, dataframe=dataframe)
            sheets.append((sheet_name, normalized_dataframe))

        if not sheets:
            raise HTTPException(status_code=400, detail="Workbook does not contain any sheets.")
        return sheets

    def _normalize_dataframe_columns(self, *, sheet_name: str, dataframe: pd.DataFrame) -> pd.DataFrame:
        normalized_columns: list[str] = []
        for column in dataframe.columns:
            cleaned = " ".join(str(column).split()).strip()
            if not cleaned or cleaned.lower() == "nan":
                raise HTTPException(status_code=400, detail=f"Sheet '{sheet_name}' contains an empty column header.")
            normalized_columns.append(cleaned)

        duplicates = sorted({column for column in normalized_columns if normalized_columns.count(column) > 1})
        if duplicates:
            raise HTTPException(
                status_code=400,
                detail=f"Sheet '{sheet_name}' contains duplicate columns after normalization: {duplicates}.",
            )

        dataframe = dataframe.copy()
        dataframe.columns = normalized_columns
        return dataframe

    def _stage_workbook(self, bundles: list[SheetBundle]) -> tuple[ImportReport, StagedWorkbook]:
        staged = StagedWorkbook()
        sheet_reports: list[SheetImportReport] = []
        all_errors: list[RowError] = []

        for bundle in bundles:
            sheet_report = self._stage_sheet(bundle=bundle, staged=staged)
            sheet_reports.append(sheet_report)
            all_errors.extend(sheet_report.errors)

        processed_rows = sum(sheet.processed_rows for sheet in sheet_reports)
        failed_rows = sum(sheet.failed_rows for sheet in sheet_reports)

        return (
            ImportReport(
                status=ImportStatus.SUCCESS,
                processed_rows=processed_rows,
                failed_rows=failed_rows,
                errors=all_errors,
                sheets=sheet_reports,
            ),
            staged,
        )

    def _stage_sheet(self, *, bundle: SheetBundle, staged: StagedWorkbook) -> SheetImportReport:
        report = SheetImportReport(
            sheet_name=bundle.sheet_name,
            file_type=bundle.analysis.file_type,
            format=bundle.analysis.format,
        )

        parsed_mappings = {
            column: parse_column_mapping(token)
            for column, token in bundle.analysis.columns.items()
        }

        attendance_values = bundle.analysis.attendance_values
        for row_number, row_values in enumerate(bundle.dataframe.itertuples(index=False, name=None), start=2):
            row = dict(zip(bundle.dataframe.columns, row_values, strict=True))
            row_errors: list[str] = []

            if self._row_is_empty(row):
                self._record_error(report, bundle.sheet_name, row_number, "Row is empty.")
                report.failed_rows += 1
                continue

            try:
                roll_number = self._extract_roll_number(row=row, analysis=bundle.analysis)
            except ValueError as exc:
                self._record_error(report, bundle.sheet_name, row_number, str(exc))
                report.failed_rows += 1
                continue

            student_name = self._extract_name(row=row, parsed_mappings=parsed_mappings)
            self._stage_student(staged=staged, roll_number=roll_number, name=student_name)

            staged_record_count = 0
            row_date = self._extract_row_date(row=row, parsed_mappings=parsed_mappings, row_errors=row_errors)
            date_required = self._find_column_by_kind(parsed_mappings, "date") is not None

            staged_record_count += self._stage_long_row(
                staged=staged,
                parsed_mappings=parsed_mappings,
                row=row,
                roll_number=roll_number,
                row_date=row_date,
                date_required=date_required,
                attendance_values=attendance_values,
                row_errors=row_errors,
            )
            staged_record_count += self._stage_dynamic_row(
                staged=staged,
                parsed_mappings=parsed_mappings,
                row=row,
                roll_number=roll_number,
                row_date=row_date,
                date_required=date_required,
                attendance_values=attendance_values,
                row_errors=row_errors,
            )

            if staged_record_count == 0:
                row_errors.append("No importable values found in row.")
                self._record_error(report, bundle.sheet_name, row_number, "; ".join(row_errors))
                report.failed_rows += 1
                continue

            if row_errors:
                self._record_error(report, bundle.sheet_name, row_number, "; ".join(row_errors))
            report.processed_rows += 1

        return report

    def _stage_long_row(
        self,
        *,
        staged: StagedWorkbook,
        parsed_mappings: dict[str, ParsedColumnMapping],
        row: dict[str, Any],
        roll_number: str,
        row_date: date | None,
        date_required: bool,
        attendance_values: list[str],
        row_errors: list[str],
    ) -> int:
        subject_column = self._find_column_by_kind(parsed_mappings, "subject")
        if not subject_column:
            return 0

        subject_name = self._normalize_subject_name(row.get(subject_column))
        if not subject_name:
            row_errors.append("Subject value is missing.")
            return 0

        staged_count = 0
        marks_column = self._find_column_by_kind(parsed_mappings, "marks")
        attendance_column = self._find_column_by_kind(parsed_mappings, "attendance")
        percentage_column = self._find_column_by_kind(parsed_mappings, "percentage")

        if marks_column and not self._is_empty(row.get(marks_column)):
            marks_value = self._parse_float(row.get(marks_column), field_name=marks_column)
            if marks_value is None:
                row_errors.append(f"Invalid numeric marks value in column '{marks_column}'.")
            elif self._stage_mark(staged=staged, roll_number=roll_number, subject_name=subject_name, marks=marks_value):
                staged_count += 1
            else:
                row_errors.append(f"Conflicting duplicate marks entry for subject '{subject_name}'.")

        if attendance_column and not self._is_empty(row.get(attendance_column)):
            if date_required and row_date is None:
                row_errors.append("Attendance date is missing or invalid.")
            else:
                status = self._parse_attendance_status(row.get(attendance_column), attendance_values, row_errors, attendance_column)
                if status:
                    if self._stage_attendance(
                        staged=staged,
                        roll_number=roll_number,
                        subject_name=subject_name,
                        date_value=row_date,
                        status=status,
                        percentage=None,
                    ):
                        staged_count += 1
                    else:
                        row_errors.append(f"Conflicting duplicate attendance entry for subject '{subject_name}'.")

        if percentage_column and not self._is_empty(row.get(percentage_column)):
            if date_required and row_date is None:
                row_errors.append("Attendance date is missing or invalid.")
            else:
                percentage = self._parse_percentage(row.get(percentage_column), field_name=percentage_column)
                if percentage is None:
                    row_errors.append(f"Invalid attendance percentage in column '{percentage_column}'.")
                elif self._stage_attendance(
                    staged=staged,
                    roll_number=roll_number,
                    subject_name=subject_name,
                    date_value=row_date,
                    status=None,
                    percentage=percentage,
                ):
                    staged_count += 1
                else:
                    row_errors.append(f"Conflicting duplicate attendance entry for subject '{subject_name}'.")

        return staged_count

    def _stage_dynamic_row(
        self,
        *,
        staged: StagedWorkbook,
        parsed_mappings: dict[str, ParsedColumnMapping],
        row: dict[str, Any],
        roll_number: str,
        row_date: date | None,
        date_required: bool,
        attendance_values: list[str],
        row_errors: list[str],
    ) -> int:
        staged_count = 0

        for column_name, mapping in parsed_mappings.items():
            if self._is_empty(row.get(column_name)):
                continue

            if mapping.kind == "subject_marks":
                marks_value = self._parse_float(row.get(column_name), field_name=column_name)
                if marks_value is None:
                    row_errors.append(f"Invalid numeric marks value in column '{column_name}'.")
                    continue
                if self._stage_mark(
                    staged=staged,
                    roll_number=roll_number,
                    subject_name=mapping.subject or column_name,
                    marks=marks_value,
                ):
                    staged_count += 1
                else:
                    row_errors.append(f"Conflicting duplicate marks entry for subject '{mapping.subject}'.")

            elif mapping.kind == "subject_attendance":
                if date_required and row_date is None:
                    row_errors.append("Attendance date is missing or invalid.")
                    continue
                status = self._parse_attendance_status(row.get(column_name), attendance_values, row_errors, column_name)
                if not status:
                    continue
                if self._stage_attendance(
                    staged=staged,
                    roll_number=roll_number,
                    subject_name=mapping.subject or column_name,
                    date_value=row_date,
                    status=status,
                    percentage=None,
                ):
                    staged_count += 1
                else:
                    row_errors.append(f"Conflicting duplicate attendance entry for subject '{mapping.subject}'.")

            elif mapping.kind == "subject_percentage":
                if date_required and row_date is None:
                    row_errors.append("Attendance date is missing or invalid.")
                    continue
                percentage = self._parse_percentage(row.get(column_name), field_name=column_name)
                if percentage is None:
                    row_errors.append(f"Invalid attendance percentage in column '{column_name}'.")
                    continue
                if self._stage_attendance(
                    staged=staged,
                    roll_number=roll_number,
                    subject_name=mapping.subject or column_name,
                    date_value=row_date,
                    status=None,
                    percentage=percentage,
                ):
                    staged_count += 1
                else:
                    row_errors.append(f"Conflicting duplicate attendance entry for subject '{mapping.subject}'.")

        return staged_count

    def _persist_staged_data(self, staged: StagedWorkbook) -> None:
        with self.db.begin():
            self._upsert_students(staged.students)
            self._upsert_subjects(staged.subjects)
            student_id_map = self._fetch_student_ids(list(staged.students))
            subject_id_map = self._fetch_subject_ids(staged.subjects)
            self._upsert_marks(staged.marks, student_id_map, subject_id_map)
            self._upsert_attendance(staged.attendance, student_id_map, subject_id_map)

    def _upsert_students(self, student_map: dict[str, StudentDraft]) -> None:
        if not student_map:
            return

        values = [{"roll_number": draft.roll_number, "name": draft.name} for draft in student_map.values()]
        statement = insert(Student).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[Student.roll_number],
            set_={"name": func.coalesce(statement.excluded.name, Student.name)},
        )
        self.db.execute(statement)

    def _upsert_subjects(self, subject_map: dict[str, str]) -> None:
        if not subject_map:
            return

        existing_subjects = self._fetch_subject_ids(subject_map)
        missing_subjects = [
            {"name": subject_name}
            for subject_key, subject_name in subject_map.items()
            if subject_key not in existing_subjects
        ]
        if not missing_subjects:
            return

        statement = insert(Subject).values(missing_subjects)
        statement = statement.on_conflict_do_nothing(index_elements=[Subject.name])
        self.db.execute(statement)

    def _upsert_marks(
        self,
        mark_map: dict[tuple[str, str], MarkDraft],
        student_id_map: dict[str, int],
        subject_id_map: dict[str, int],
    ) -> None:
        if not mark_map:
            return

        payloads = [
            {
                "student_id": student_id_map[draft.roll_number],
                "subject_id": subject_id_map[draft.subject_key],
                "marks": draft.marks,
            }
            for draft in mark_map.values()
        ]

        for payload_chunk in self._chunk(payloads):
            statement = insert(Mark).values(payload_chunk)
            statement = statement.on_conflict_do_update(
                index_elements=[Mark.student_id, Mark.subject_id],
                set_={"marks": statement.excluded.marks},
            )
            self.db.execute(statement)

    def _upsert_attendance(
        self,
        attendance_map: dict[tuple[str, str, date | None], AttendanceDraft],
        student_id_map: dict[str, int],
        subject_id_map: dict[str, int],
    ) -> None:
        if not attendance_map:
            return

        dated_payloads: list[dict[str, Any]] = []
        undated_payloads: list[dict[str, Any]] = []

        for draft in attendance_map.values():
            payload = {
                "student_id": student_id_map[draft.roll_number],
                "subject_id": subject_id_map[draft.subject_key],
                "date": draft.date_value,
                "status": draft.status,
                "percentage": draft.percentage,
            }
            if draft.date_value is None:
                undated_payloads.append(payload)
            else:
                dated_payloads.append(payload)

        for payload_chunk in self._chunk(dated_payloads):
            statement = insert(Attendance).values(payload_chunk)
            statement = statement.on_conflict_do_update(
                index_elements=[Attendance.student_id, Attendance.subject_id, Attendance.date],
                set_={"status": statement.excluded.status, "percentage": statement.excluded.percentage},
            )
            self.db.execute(statement)

        for payload_chunk in self._chunk(undated_payloads):
            statement = insert(Attendance).values(payload_chunk)
            statement = statement.on_conflict_do_update(
                index_elements=[Attendance.student_id, Attendance.subject_id],
                index_where=Attendance.date.is_(None),
                set_={"status": statement.excluded.status, "percentage": statement.excluded.percentage},
            )
            self.db.execute(statement)

    def _fetch_student_ids(self, roll_numbers: list[str]) -> dict[str, int]:
        if not roll_numbers:
            return {}
        query = select(Student.roll_number, Student.id).where(Student.roll_number.in_(roll_numbers))
        return {roll_number: student_id for roll_number, student_id in self.db.execute(query)}

    def _fetch_subject_ids(self, subject_map: dict[str, str]) -> dict[str, int]:
        if not subject_map:
            return {}

        query = select(Subject.id, Subject.name).where(func.lower(Subject.name).in_(list(subject_map)))
        subject_ids: dict[str, int] = {}
        for subject_id, subject_name in self.db.execute(query).all():
            key = self._subject_key(subject_name)
            if key in subject_map:
                subject_ids[key] = subject_id
        return subject_ids

    def _stage_student(self, *, staged: StagedWorkbook, roll_number: str, name: str | None) -> None:
        existing = staged.students.get(roll_number)
        if not existing:
            staged.students[roll_number] = StudentDraft(roll_number=roll_number, name=name)
            return
        if name:
            existing.name = name

    def _stage_mark(self, *, staged: StagedWorkbook, roll_number: str, subject_name: str, marks: float) -> bool:
        normalized_subject = self._normalize_subject_name(subject_name)
        if not normalized_subject:
            return False
        subject_key = self._subject_key(normalized_subject)
        staged.subjects.setdefault(subject_key, normalized_subject)
        key = (roll_number, subject_key)
        existing = staged.marks.get(key)
        if existing:
            return abs(existing.marks - marks) < 1e-9

        staged.marks[key] = MarkDraft(
            roll_number=roll_number,
            subject_key=subject_key,
            subject_name=normalized_subject,
            marks=marks,
        )
        return True

    def _stage_attendance(
        self,
        *,
        staged: StagedWorkbook,
        roll_number: str,
        subject_name: str,
        date_value: date | None,
        status: AttendanceStatus | None,
        percentage: float | None,
    ) -> bool:
        normalized_subject = self._normalize_subject_name(subject_name)
        if not normalized_subject:
            return False
        subject_key = self._subject_key(normalized_subject)
        staged.subjects.setdefault(subject_key, normalized_subject)
        key = (roll_number, subject_key, date_value)
        existing = staged.attendance.get(key)
        if existing:
            return existing.status == status and existing.percentage == percentage

        staged.attendance[key] = AttendanceDraft(
            roll_number=roll_number,
            subject_key=subject_key,
            subject_name=normalized_subject,
            date_value=date_value,
            status=status,
            percentage=percentage,
        )
        return True

    def _extract_roll_number(self, *, row: dict[str, Any], analysis: AIAnalysisResponse) -> str:
        value = row.get(analysis.primary_key)
        cleaned = self._normalize_identifier(value)
        if not cleaned:
            raise ValueError("Missing roll number.")
        return cleaned

    def _extract_name(self, *, row: dict[str, Any], parsed_mappings: dict[str, ParsedColumnMapping]) -> str | None:
        name_column = self._find_column_by_kind(parsed_mappings, "name")
        if not name_column:
            return None
        return self._normalize_text(row.get(name_column))

    def _extract_row_date(
        self,
        *,
        row: dict[str, Any],
        parsed_mappings: dict[str, ParsedColumnMapping],
        row_errors: list[str],
    ) -> date | None:
        date_column = self._find_column_by_kind(parsed_mappings, "date")
        if not date_column or self._is_empty(row.get(date_column)):
            return None

        parsed = pd.to_datetime(row.get(date_column), errors="coerce")
        if pd.isna(parsed):
            row_errors.append(f"Invalid date value in column '{date_column}'.")
            return None
        return parsed.date()

    def _find_column_by_kind(self, parsed_mappings: dict[str, ParsedColumnMapping], kind: str) -> str | None:
        for column_name, mapping in parsed_mappings.items():
            if mapping.kind == kind:
                return column_name
        return None

    def _parse_float(self, value: Any, *, field_name: str) -> float | None:
        if self._is_empty(value):
            return None
        candidate = value.strip().replace(",", "") if isinstance(value, str) else value
        try:
            parsed = float(candidate)
        except (TypeError, ValueError):
            logger.warning("Invalid float value for field '%s': %s", field_name, value)
            return None
        if not math.isfinite(parsed) or parsed < 0:
            logger.warning("Out-of-range marks value for field '%s': %s", field_name, value)
            return None
        return parsed

    def _parse_percentage(self, value: Any, *, field_name: str) -> float | None:
        if self._is_empty(value):
            return None
        candidate = value.strip().replace("%", "").replace(",", "") if isinstance(value, str) else value
        try:
            parsed = float(candidate)
        except (TypeError, ValueError):
            logger.warning("Invalid percentage value for field '%s': %s", field_name, value)
            return None
        if not math.isfinite(parsed) or not 0 <= parsed <= 100:
            logger.warning("Out-of-range percentage value for field '%s': %s", field_name, value)
            return None
        return parsed

    def _parse_attendance_status(
        self,
        value: Any,
        attendance_values: list[str],
        row_errors: list[str],
        column_name: str,
    ) -> AttendanceStatus | None:
        if self._is_empty(value):
            return None

        cleaned = str(value).strip()
        if not cleaned:
            return None

        token_map = self._build_attendance_token_map(attendance_values)
        status = token_map.get(cleaned.casefold())
        if not status:
            row_errors.append(f"Unknown attendance value '{cleaned}' in column '{column_name}'.")
            return None
        return status

    def _build_attendance_token_map(self, attendance_values: list[str]) -> dict[str, AttendanceStatus]:
        token_map = {
            "p": AttendanceStatus.PRESENT,
            "present": AttendanceStatus.PRESENT,
            "a": AttendanceStatus.ABSENT,
            "absent": AttendanceStatus.ABSENT,
        }
        if len(attendance_values) >= 2:
            token_map[attendance_values[0].casefold()] = AttendanceStatus.PRESENT
            token_map[attendance_values[1].casefold()] = AttendanceStatus.ABSENT
        return token_map

    def _validate_file_name(self, file_name: str | None) -> None:
        if not file_name:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
        extension = f".{file_name.rsplit('.', 1)[-1].lower()}" if "." in file_name else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Only Excel files (.xlsx, .xls, .xlsm, .xlsb) are supported.")

    def _record_error(self, report: SheetImportReport, sheet_name: str, row_number: int, message: str) -> None:
        logger.warning("Import validation error on sheet '%s' row %s: %s", sheet_name, row_number, message)
        report.errors.append(RowError(sheet=sheet_name, row=row_number, error=message))

    def _row_is_empty(self, row: dict[str, Any]) -> bool:
        return all(self._is_empty(value) for value in row.values())

    def _is_empty(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        try:
            return bool(pd.isna(value))
        except TypeError:
            return False

    def _normalize_identifier(self, value: Any) -> str | None:
        normalized = self._normalize_text(value)
        if not normalized:
            return None
        return normalized.upper()

    def _normalize_text(self, value: Any) -> str | None:
        if self._is_empty(value):
            return None
        return " ".join(str(value).split()).strip()

    def _normalize_subject_name(self, value: Any) -> str | None:
        return self._normalize_text(value)

    def _subject_key(self, subject_name: str) -> str:
        return " ".join(subject_name.split()).strip().casefold()

    def _chunk(self, payloads: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        return [payloads[index : index + settings.row_chunk_size] for index in range(0, len(payloads), settings.row_chunk_size)]

    def _determine_report_status(self, report: ImportReport) -> ImportStatus:
        if report.processed_rows == 0:
            return ImportStatus.FAILED
        if report.failed_rows > 0 or report.errors:
            return ImportStatus.PARTIAL
        return ImportStatus.SUCCESS
