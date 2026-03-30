from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pandas as pd
from fastapi import HTTPException

from database import settings
from schemas import AIAnalysisResponse, FileType, ParsedColumnMapping, SheetFormat, parse_column_mapping


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a strict Excel structure analyzer. Return ONLY valid JSON.\n"
    "Rules:\n"
    "1. Use only the provided columns and sample rows.\n"
    "2. Return mappings for every provided column. Use 'ignore' for extra columns.\n"
    "3. The primary_key must be an existing column and that same column must map to 'roll_number'.\n"
    "4. Allowed file_type values: marks, attendance, mixed.\n"
    "5. Allowed format values: wide, long, summary, daily.\n"
    "6. Allowed value_type values: marks, attendance, percentage.\n"
    "7. Allowed mapped field values are: roll_number, name, subject, marks, attendance, percentage, date, ignore,\n"
    "   subject_marks:<subject_name>, subject_attendance:<subject_name>, subject_percentage:<subject_name>.\n"
    "8. For wide sheets, every subject-bearing column must use one of the subject_* mappings and the subjects array must list those subject names.\n"
    "9. For long sheets, use a 'subject' column plus marks/attendance/percentage/date columns when present.\n"
    "10. If the file contains marks or mixed data, subjects must be a non-empty array.\n"
    "11. attendance_values must contain the exact attendance tokens from the sheet when status values are present, usually ['P', 'A'].\n"
    "12. has_dates must be true only when an actual date column exists.\n"
    "13. Never invent columns, never infer missing columns, never add explanations.\n"
    "Return ONLY a JSON object with keys: file_type, format, primary_key, columns, subjects, value_type, attendance_values, has_dates."
)


class GroqAIService:
    async def analyze_sheet(self, sheet_name: str, dataframe: pd.DataFrame) -> AIAnalysisResponse:
        if not settings.groq_api_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured.")

        request_payload = {
            "sheet_name": sheet_name,
            "columns": list(dataframe.columns),
            "sample_rows": self._build_sample_rows(dataframe),
        }
        logger.info("Sending Groq structure analysis request for sheet '%s'.", sheet_name)
        logger.debug("Groq request payload for sheet '%s': %s", sheet_name, request_payload)

        body = {
            "model": settings.groq_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(request_payload, ensure_ascii=True, default=str),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.post(settings.groq_endpoint, headers=headers, json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Groq API request failed for sheet '%s': %s", sheet_name, exc)
            raise HTTPException(status_code=502, detail=f"Groq API request failed for sheet '{sheet_name}'.") from exc

        payload = response.json()
        content = self._extract_content(payload)
        logger.info("Received Groq structure analysis for sheet '%s'.", sheet_name)
        logger.debug("Groq raw response for sheet '%s': %s", sheet_name, content)

        try:
            parsed_json = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("Groq returned invalid JSON for sheet '%s': %s", sheet_name, content)
            raise HTTPException(status_code=400, detail=f"AI returned invalid JSON for sheet '{sheet_name}'.") from exc

        try:
            analysis = AIAnalysisResponse.model_validate(parsed_json)
            self._validate_against_dataframe(sheet_name=sheet_name, analysis=analysis, dataframe=dataframe)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("AI validation failed for sheet '%s'. Response: %s", sheet_name, parsed_json, exc_info=exc)
            raise HTTPException(status_code=400, detail=f"Invalid AI response for sheet '{sheet_name}': {exc}") from exc

        return analysis

    def _build_sample_rows(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        sample_rows: list[dict[str, Any]] = []
        for _, row in dataframe.iterrows():
            row_dict = {column: self._serialize_value(row[column]) for column in dataframe.columns}
            if any(value is not None for value in row_dict.values()):
                sample_rows.append(row_dict)
            if len(sample_rows) >= settings.sample_row_limit:
                break
        return sample_rows

    def _serialize_value(self, value: Any) -> Any:
        if pd.isna(value):
            return None
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except TypeError:
                return str(value)
        return value

    def _extract_content(self, payload: dict[str, Any]) -> str:
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Unexpected Groq API payload: %s", payload)
            raise HTTPException(status_code=502, detail="Groq API returned an unexpected response payload.") from exc

    def _validate_against_dataframe(
        self,
        *,
        sheet_name: str,
        analysis: AIAnalysisResponse,
        dataframe: pd.DataFrame,
    ) -> None:
        dataframe_columns = list(dataframe.columns)
        dataframe_column_set = set(dataframe_columns)

        if set(analysis.columns.keys()) != dataframe_column_set:
            missing = sorted(dataframe_column_set.difference(analysis.columns.keys()))
            extra = sorted(set(analysis.columns.keys()).difference(dataframe_column_set))
            raise ValueError(
                f"columns mapping must cover every dataframe column. Missing mappings: {missing}. Unexpected mappings: {extra}."
            )

        if analysis.primary_key not in dataframe_column_set:
            raise ValueError(f"primary_key '{analysis.primary_key}' does not exist in sheet '{sheet_name}'.")

        if analysis.columns.get(analysis.primary_key) != "roll_number":
            raise ValueError("primary_key must map to 'roll_number'.")

        parsed_mappings: dict[str, ParsedColumnMapping] = {
            column: parse_column_mapping(mapped_value)
            for column, mapped_value in analysis.columns.items()
        }

        kind_counts: dict[str, int] = {}
        subject_tokens: set[str] = set()
        has_marks_mapping = False
        has_attendance_mapping = False
        has_percentage_mapping = False

        for parsed in parsed_mappings.values():
            kind_counts[parsed.kind] = kind_counts.get(parsed.kind, 0) + 1
            if parsed.kind in {"marks", "subject_marks"}:
                has_marks_mapping = True
            if parsed.kind in {"attendance", "subject_attendance"}:
                has_attendance_mapping = True
            if parsed.kind in {"percentage", "subject_percentage"}:
                has_percentage_mapping = True
            if parsed.subject:
                subject_tokens.add(parsed.subject.casefold())

        if analysis.format == SheetFormat.WIDE and not subject_tokens:
            raise ValueError("wide format requires subject_* column mappings.")

        if analysis.format in {SheetFormat.LONG, SheetFormat.DAILY} and "subject" not in kind_counts and not subject_tokens:
            raise ValueError("long/daily format requires a mapped 'subject' column or subject_* column mappings.")

        if analysis.has_dates and "date" not in kind_counts:
            raise ValueError("has_dates is true but no column is mapped to 'date'.")

        if not analysis.has_dates and "date" in kind_counts:
            raise ValueError("has_dates is false but a column is mapped to 'date'.")

        if analysis.file_type == FileType.MARKS:
            if not has_marks_mapping:
                raise ValueError("marks files must include marks mappings.")
            if has_attendance_mapping or has_percentage_mapping:
                raise ValueError("marks files cannot include attendance or percentage mappings.")

        if analysis.file_type == FileType.ATTENDANCE:
            if has_marks_mapping:
                raise ValueError("attendance files cannot include marks mappings.")
            if not (has_attendance_mapping or has_percentage_mapping):
                raise ValueError("attendance files must include attendance or percentage mappings.")

        if analysis.file_type == FileType.MIXED and not (has_marks_mapping and (has_attendance_mapping or has_percentage_mapping)):
            raise ValueError("mixed files must include both marks and attendance/percentage mappings.")

        if analysis.file_type in {FileType.MARKS, FileType.MIXED} and not analysis.subjects:
            raise ValueError("subjects must be present for marks or mixed files.")

        if subject_tokens and analysis.subjects:
            missing_subjects = sorted(subject_tokens.difference({subject.casefold() for subject in analysis.subjects}))
            if missing_subjects:
                raise ValueError(f"subjects array must include all subject_* mappings. Missing: {missing_subjects}.")

        if has_attendance_mapping and len(analysis.attendance_values) < 2:
            raise ValueError("attendance_values must include present and absent tokens for attendance mappings.")

        if analysis.file_type != FileType.MIXED:
            if analysis.value_type.value == "marks" and not has_marks_mapping:
                raise ValueError("value_type 'marks' requires marks mappings.")
            if analysis.value_type.value == "attendance" and not has_attendance_mapping:
                raise ValueError("value_type 'attendance' requires attendance mappings.")
            if analysis.value_type.value == "percentage" and not has_percentage_mapping:
                raise ValueError("value_type 'percentage' requires percentage mappings.")
