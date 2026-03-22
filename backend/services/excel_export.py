"""Build .xlsx bytes using openpyxl only (no pandas)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook


def _normalize_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return value


def workbook_bytes_from_rows(rows: list[dict[str, Any]], sheet_name: str = "Sheet1") -> bytes:
    """
    Serialize rows to an Excel workbook.

    Empty `rows` still produces a sheet with a short notice (valid workbook for download).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    if not rows:
        ws.append(["Message"])
        ws.append(["No data matched the current filters."])
    else:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([_normalize_cell(row.get(h)) for h in headers])

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
