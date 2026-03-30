from __future__ import annotations

import io
import logging
import random
import secrets
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth.security import hash_password
from models.entities import Student, StudentSubject, Subject, Teacher, TeacherStudent, User, UserRole

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "Name",
    "Email",
    "Department",
    "Year",
    "Section",
    "Attendance",
    "CGPA",
    "Backlogs",
]

SUBJECT_BLUEPRINTS = [
    ("Mathematics I", "MATH101", 1),
    ("Programming Fundamentals", "CSE101", 1),
    ("Digital Logic", "ECE101", 1),
    ("Data Structures", "CSE201", 2),
    ("Database Systems", "CSE202", 2),
    ("Operating Systems", "CSE301", 3),
]


@dataclass
class ParsedRow:
    name: str
    email: str
    department: str
    year: int
    section: str
    attendance: float
    cgpa: float
    backlogs: int


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for col in df.columns:
        normalized = str(col).strip()
        for required in REQUIRED_COLUMNS:
            if normalized.lower() == required.lower():
                mapping[col] = required
                break
    return df.rename(columns=mapping)


def _validate_sheet(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
    return errors


def _is_empty_row(series: pd.Series) -> bool:
    return all(pd.isna(v) or str(v).strip() == "" for v in series.tolist())


def _parse_row(series: pd.Series, row_number: int) -> tuple[ParsedRow | None, str | None]:
    try:
        name = str(series["Name"]).strip()
        email = str(series["Email"]).strip().lower()
        department = str(series["Department"]).strip()
        section = str(series["Section"]).strip()
        year = int(float(series["Year"]))
        attendance = float(series["Attendance"])
        cgpa = float(series["CGPA"])
        backlogs = int(float(series["Backlogs"]))
    except (TypeError, ValueError) as exc:
        return None, f"row {row_number}: invalid data type ({exc})"

    if not name:
        return None, f"row {row_number}: Name is required"
    if "@" not in email or "." not in email.split("@")[-1]:
        return None, f"row {row_number}: invalid email '{email}'"
    if not department:
        return None, f"row {row_number}: Department is required"
    if not section:
        return None, f"row {row_number}: Section is required"
    if year < 1 or year > 8:
        return None, f"row {row_number}: Year must be between 1 and 8"
    if attendance < 0 or attendance > 100:
        return None, f"row {row_number}: Attendance must be between 0 and 100"
    if cgpa < 0 or cgpa > 10:
        return None, f"row {row_number}: CGPA must be between 0 and 10"
    if backlogs < 0:
        return None, f"row {row_number}: Backlogs must be >= 0"

    return ParsedRow(
        name=name,
        email=email,
        department=department,
        year=year,
        section=section,
        attendance=round(attendance, 2),
        cgpa=round(cgpa, 2),
        backlogs=backlogs,
    ), None


def _ensure_subject_catalog(db: Session) -> list[Subject]:
    existing_codes = set(db.scalars(select(Subject.code)).all())
    for name, code, semester in SUBJECT_BLUEPRINTS:
        if code in existing_codes:
            continue
        db.add(Subject(name=name, code=code, semester=semester))
    db.flush()
    return db.query(Subject).order_by(Subject.semester.asc(), Subject.name.asc()).limit(6).all()


def _choose_teacher(db: Session, current_user: User, teacher_id: int | None) -> Teacher:
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise ValueError("Teacher profile not found for current account.")
        return teacher

    teachers = db.query(Teacher).order_by(Teacher.id.asc()).all()
    if not teachers:
        raise ValueError("No teachers found. Create at least one teacher before upload.")
    if teacher_id is not None:
        selected = next((t for t in teachers if t.id == teacher_id), None)
        if not selected:
            raise ValueError(f"Invalid teacher_id {teacher_id}.")
        return selected
    return random.choice(teachers)


def _unique_roll_number(db: Session, year: int) -> str:
    for _ in range(20):
        candidate = f"UP{year}{secrets.token_hex(3).upper()}"
        exists = db.query(Student.id).filter(Student.roll_number == candidate).first()
        if not exists:
            return candidate
    raise ValueError("Could not generate unique roll number.")


def _persist_student_row(db: Session, parsed: ParsedRow, teacher: Teacher) -> None:
    password = "Password@123"
    user = User(
        name=parsed.name,
        email=parsed.email,
        password=hash_password(password),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()

    student = Student(
        user_id=user.id,
        roll_number=_unique_roll_number(db, parsed.year),
        department=parsed.department,
        year=parsed.year,
        section=parsed.section,
    )
    db.add(student)
    db.flush()
    db.add(TeacherStudent(teacher_id=teacher.id, student_id=student.id))
    # Assign initial subjects (first 6) for manual entry prep, consistent with manual creation
    for subject in db.query(Subject).order_by(Subject.semester.asc()).limit(6).all():
        db.add(StudentSubject(student_id=student.id, subject_id=subject.id))


def process_excel_upload(
    db: Session,
    current_user: User,
    filename: str,
    content: bytes,
    teacher_id: int | None = None,
) -> dict:
    if not filename.lower().endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
        raise ValueError("Only Excel files (.xlsx/.xlsm) are supported.")
    if not content:
        raise ValueError("Uploaded file is empty.")

    try:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Could not read Excel file: {exc}") from exc

    df = _normalize_columns(df)
    sheet_errors = _validate_sheet(df)
    if sheet_errors:
        return {
            "total_rows": 0,
            "success": 0,
            "failed": len(sheet_errors),
            "errors": sheet_errors,
        }

    teacher = _choose_teacher(db, current_user, teacher_id)

    seen_emails: set[str] = set()
    success = 0
    failed = 0
    errors: list[str] = []
    total_rows = int(df.shape[0])

    for idx, row in df.iterrows():
        row_number = idx + 2  # 1-based + header
        if _is_empty_row(row):
            continue

        parsed, err = _parse_row(row, row_number)
        if err:
            failed += 1
            errors.append(err)
            continue
        assert parsed is not None

        if parsed.email in seen_emails:
            failed += 1
            errors.append(f"row {row_number}: duplicate email in file '{parsed.email}'")
            continue
        seen_emails.add(parsed.email)

        if db.query(User.id).filter(User.email == parsed.email).first():
            failed += 1
            errors.append(f"row {row_number}: email already exists '{parsed.email}'")
            continue

        try:
            _persist_student_row(db, parsed, teacher)
            db.commit()
            success += 1
        except IntegrityError as exc:
            db.rollback()
            failed += 1
            logger.warning("Upload row integrity error row=%s email=%s: %s", row_number, parsed.email, exc)
            errors.append(f"row {row_number}: data conflict for '{parsed.email}'")
        except (ValueError, SQLAlchemyError) as exc:
            db.rollback()
            failed += 1
            logger.warning("Upload row failed row=%s email=%s: %s", row_number, parsed.email, exc)
            errors.append(f"row {row_number}: {exc}")
        except Exception as exc:  # defensive catch to avoid aborting full upload batch
            db.rollback()
            failed += 1
            logger.exception("Unexpected upload row error row=%s email=%s", row_number, parsed.email)
            errors.append(f"row {row_number}: unexpected error ({type(exc).__name__})")

    return {
        "total_rows": total_rows,
        "success": success,
        "failed": failed,
        "errors": errors[:200],  # cap payload size
    }
