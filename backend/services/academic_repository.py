"""
academic_repository.py
======================
Data-access layer for the intelligent Excel import pipeline.

Design principles
-----------------
* All queries are isolated here; business logic lives in excel_import_service.py.
* Bulk pre-load helpers populate in-memory caches so the service layer never
  issues individual SELECT statements inside a hot loop.
* Every write helper flushes (not commits) so the caller controls transactions.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.security import hash_password
from models.entities import (
    AcademicRecord,
    ImportAudit,
    ImportStatus,
    Student,
    StudentSubject,
    Subject,
    Teacher,
    TeacherStudent,
    SemesterResult,
    User,
    UserRole,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Type aliases for cache maps used by the service
# ──────────────────────────────────────────────
StudentCache = dict[str, Student]          # roll_number → Student
SubjectCache = dict[str, Subject]          # name_lower   → Subject
RecordCache  = dict[tuple, AcademicRecord] # (student_id, subject_id, semester) → AcademicRecord


# ══════════════════════════════════════════════════════════════════════════════
# BULK LOADERS  (call once per import; eliminate per-row SELECT queries)
# ══════════════════════════════════════════════════════════════════════════════

def load_subject_cache(db: Session, names: list[str] | None = None) -> SubjectCache:
    """
    Return {name_lower: Subject} for subjects.
    If 'names' is provided, only fetch those subjects (Scoped Loading).
    """
    q = db.query(Subject)
    if names:
        q = q.filter(Subject.name.in_(names))
    subjects = q.all()
    return {s.name.lower(): s for s in subjects}


def load_student_cache_scoped(db: Session, roll_numbers: list[str]) -> StudentCache:
    """Fetch only the students present in the current import file by roll_number."""
    if not roll_numbers:
        return {}
    rows = (
        db.query(Student)
        .filter(Student.roll_number.in_(roll_numbers))
        .all()
    )
    return {s.roll_number.upper(): s for s in rows}

def load_record_cache_scoped(db: Session, student_ids: list[int]) -> RecordCache:
    """Fetch academic records only for students being touched in this import."""
    if not student_ids:
        return {}
    records = db.query(AcademicRecord).filter(AcademicRecord.student_id.in_(student_ids)).all()
    return {
        (r.student_id, r.subject_id, r.semester): r
        for r in records
    }


# ══════════════════════════════════════════════════════════════════════════════
# SUBJECT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _generate_subject_code(name: str, semester: int) -> str:
    """Build a deterministic, short subject code from its name."""
    prefix = "".join(w[0].upper() for w in name.split()[:3] if w)
    return f"{prefix}{semester:02d}"


def get_or_create_subject(
    db: Session,
    subject_cache: SubjectCache,
    name: str,
    semester: int,
) -> Subject:
    """
    Look up a subject by name (case-insensitive).
    If missing → create it automatically and refresh cache.
    """
    key = name.strip().lower()
    if key in subject_cache:
        return subject_cache[key]

    # Auto-generate a unique code (add random suffix if collision occurs)
    base_code = _generate_subject_code(name.strip(), semester)
    code = base_code
    attempt = 0
    while db.query(Subject.id).filter(Subject.code == code).first():
        attempt += 1
        code = f"{base_code}{attempt}"

    subject = Subject(name=name.strip(), code=code, semester=semester)
    db.add(subject)
    db.flush()

    subject_cache[key] = subject
    logger.info("Auto-created subject '%s' code=%s sem=%d", name, code, semester)
    return subject


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_or_create_student(
    db: Session,
    student_cache: StudentCache,
    *,
    name: str,
    email: str | None,
    department: str,
    year: int,
    section: str,
    roll_number: str,
    cgpa: float = 0.0,
    sgpa: float = 0.0,
) -> tuple[Student, bool]:
    """
    Fetch student by roll_number from cache.
    If not found → create User + Student records (flush, don't commit).

    Returns (student, created: bool).
    """
    key = roll_number.strip().upper()
    if key in student_cache:
        student = student_cache[key]
        # Diff-update basic profile if anything changed
        changed = False
        if student.department != department:
            student.department = department
            changed = True
        if student.year != year:
            student.year = year
            changed = True
        if student.section != section:
            student.section = section
            changed = True
        if student.cgpa != cgpa:
            student.cgpa = cgpa
            changed = True
        if student.sgpa != sgpa:
            student.sgpa = sgpa
            changed = True
        user = db.get(User, student.user_id)
        if user and user.name != name:
            user.name = name
            changed = True
        if changed:
            db.flush()
        return student, False

    # CREATE
    user_email = email.strip().lower() if email else f"{key}@student.edu"
    user = User(
        name=name.strip(),
        email=user_email,
        password=hash_password("Password@123"),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()

    student = Student(
        user_id=user.id,
        roll_number=key,
        department=department,
        year=year,
        section=section,
        cgpa=cgpa,
        sgpa=sgpa,
    )
    db.add(student)
    db.flush()

    student_cache[key] = student
    return student, True


def ensure_teacher_link(
    db: Session,
    student: Student,
    teacher: Teacher,
) -> None:
    """Create TeacherStudent link if it doesn't already exist."""
    exists = (
        db.query(TeacherStudent.id)
        .filter(
            TeacherStudent.teacher_id == teacher.id,
            TeacherStudent.student_id == student.id,
        )
        .first()
    )
    if not exists:
        db.add(TeacherStudent(teacher_id=teacher.id, student_id=student.id))
        db.flush()


def ensure_student_subject_link(
    db: Session,
    student: Student,
    subject: Subject,
) -> None:
    """Create StudentSubject enrolment link if absent."""
    exists = (
        db.query(StudentSubject.id)
        .filter(
            StudentSubject.student_id == student.id,
            StudentSubject.subject_id == subject.id,
        )
        .first()
    )
    if not exists:
        db.add(StudentSubject(student_id=student.id, subject_id=subject.id))
        db.flush()


# ══════════════════════════════════════════════════════════════════════════════
# ACADEMIC RECORD HELPERS  (core of the diff-detection layer)
# ══════════════════════════════════════════════════════════════════════════════

def upsert_academic_record(
    db: Session,
    record_cache: RecordCache,
    *,
    student_id: int,
    subject_id: int,
    semester: int,
    marks: float,
    attendance_percentage: float,
    backlogs: int,
    detained: bool,
) -> str:
    """
    Core diff-detection logic.

    Returns one of:
        "created"  – new record inserted
        "updated"  – existing record had changed fields; updated
        "skipped"  – existing record identical; no write performed
    """
    key = (student_id, subject_id, semester)
    existing = record_cache.get(key)

    if existing is None:
        # ── INSERT ──────────────────────────────────────────────────────────
        record = AcademicRecord(
            student_id=student_id,
            subject_id=subject_id,
            semester=semester,
            marks=round(marks, 2),
            attendance_percentage=round(attendance_percentage, 2),
            backlogs=backlogs,
            detained=detained,
            last_updated_at=datetime.utcnow(),
            updated_by_import=True,
        )
        db.add(record)
        db.flush()
        record_cache[key] = record
        return "created"

    # ── DIFF CHECK ──────────────────────────────────────────────────────────
    same_marks       = round(float(existing.marks), 2)       == round(marks, 2)
    same_attendance  = round(existing.attendance_percentage, 2) == round(attendance_percentage, 2)
    same_backlogs    = existing.backlogs == backlogs
    same_detained    = existing.detained == detained

    if same_marks and same_attendance and same_backlogs and same_detained:
        # ── SKIP (idempotent) ────────────────────────────────────────────
        return "skipped"

    # ── UPDATE (only changed fields) ─────────────────────────────────────
    if not same_marks:
        existing.marks = round(marks, 2)
    if not same_attendance:
        existing.attendance_percentage = round(attendance_percentage, 2)
    if not same_backlogs:
        existing.backlogs = backlogs
    if not same_detained:
        existing.detained = detained

    existing.last_updated_at = datetime.utcnow()
    existing.updated_by_import = True
    db.flush()
    return "updated"


# ══════════════════════════════════════════════════════════════════════════════
# SEMESTER RESULT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def upsert_semester_result(
    db: Session,
    *,
    student_id: int,
    semester: int,
    sgpa: float | None,
    cgpa: float | None,
    backlogs: int | None = None,
) -> None:
    """
    Update or create the SemesterResult for a student.
    Only updates fields if they are provided (not None).
    """
    if sgpa is None and cgpa is None and backlogs is None:
        return

    existing = (
        db.query(SemesterResult)
        .filter(SemesterResult.student_id == student_id, SemesterResult.semester == semester)
        .first()
    )

    if not existing:
        res = SemesterResult(
            student_id=student_id,
            semester=semester,
            sgpa=float(sgpa) if sgpa is not None else 0.0,
            cgpa=float(cgpa) if cgpa is not None else 0.0,
            backlogs=int(backlogs) if backlogs is not None else 0,
        )
        db.add(res)
    else:
        if sgpa is not None:
            existing.sgpa = float(sgpa)
        if cgpa is not None:
            existing.cgpa = float(cgpa)
        if backlogs is not None:
            existing.backlogs = int(backlogs)
    
    db.flush()


# ══════════════════════════════════════════════════════════════════════════════
# TEACHER HELPER
# ══════════════════════════════════════════════════════════════════════════════

def resolve_teacher(
    db: Session,
    current_user: User,
    teacher_id: int | None,
) -> Teacher:
    """
    Determine which Teacher record to associate new students with.
    - TEACHER role → use their own profile.
    - ADMIN with teacher_id → use that specific teacher.
    - ADMIN without teacher_id → pick the first available teacher.
    """
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise ValueError("Teacher profile not found for the current account.")
        return teacher

    teachers = db.query(Teacher).order_by(Teacher.id.asc()).all()
    if not teachers:
        raise ValueError("No teacher profiles exist. Create at least one teacher before importing.")

    if teacher_id is not None:
        selected = next((t for t in teachers if t.id == teacher_id), None)
        if not selected:
            raise ValueError(f"teacher_id={teacher_id} does not exist.")
        return selected

    return teachers[0]


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

def create_import_audit(
    db: Session,
    *,
    uploaded_by_id: int | None,
    filename: str,
    total_rows: int = 0,
    created: int = 0,
    updated: int = 0,
    skipped: int = 0,
    failed: int = 0,
    status: ImportStatus = ImportStatus.PENDING,
    errors_json: str | None = None,
) -> ImportAudit:
    """Persist an ImportAudit row after the import finishes."""
    audit = ImportAudit(
        uploaded_by_id=uploaded_by_id,
        filename=filename,
        uploaded_at=datetime.utcnow(),
        total_rows=total_rows,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=failed,
        status=status,
        errors_json=errors_json,
    )
    db.add(audit)
    db.flush()
    return audit
