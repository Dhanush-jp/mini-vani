<<<<<<< HEAD
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import case, func
=======
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
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
from sqlalchemy.orm import Session

from auth.security import hash_password
from models.entities import (
    AcademicRecord,
<<<<<<< HEAD
    Attendance,
    AttendanceStatus,
    ImportAudit,
    ImportStatus,
    SemesterResult,
=======
    ImportAudit,
    ImportStatus,
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    Student,
    StudentSubject,
    Subject,
    Teacher,
    TeacherStudent,
<<<<<<< HEAD
=======
    SemesterResult,
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    User,
    UserRole,
)

<<<<<<< HEAD

logger = logging.getLogger(__name__)

StudentCache = dict[str, Student]
SubjectCache = dict[str, list[Subject]]
RecordCache = dict[tuple[int, int, int], AcademicRecord]
AttendanceCache = dict[tuple[int, int, date], Attendance]
DEFAULT_SUBJECT_SEMESTER = 1


def _normalize_roll_number(value: str) -> str:
    return " ".join(value.strip().split()).upper()


def _normalize_subject_name(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def load_subject_cache(db: Session, names: list[str] | None = None) -> SubjectCache:
    query = db.query(Subject)
    if names:
        normalized_names = {_normalize_subject_name(name) for name in names if name and name.strip()}
        if normalized_names:
            query = query.filter(func.lower(Subject.name).in_(normalized_names))

    cache: SubjectCache = defaultdict(list)
    for subject in query.order_by(Subject.name.asc(), Subject.semester.asc()).all():
        cache[_normalize_subject_name(subject.name)].append(subject)
    return dict(cache)


def load_student_cache_scoped(db: Session, roll_numbers: list[str]) -> StudentCache:
    normalized_rolls = {_normalize_roll_number(roll_number) for roll_number in roll_numbers if roll_number}
    if not normalized_rolls:
        return {}

    rows = db.query(Student).filter(Student.roll_number.in_(normalized_rolls)).all()
    return {student.roll_number.upper(): student for student in rows}


def load_record_cache_scoped(
    db: Session,
    student_ids: list[int],
    subject_ids: list[int] | None = None,
) -> RecordCache:
    if not student_ids:
        return {}

    query = db.query(AcademicRecord).filter(AcademicRecord.student_id.in_(student_ids))
    if subject_ids:
        query = query.filter(AcademicRecord.subject_id.in_(subject_ids))

    records = query.all()
    return {(record.student_id, record.subject_id, record.semester): record for record in records}


def load_attendance_cache_scoped(
    db: Session,
    student_ids: list[int],
    subject_ids: list[int] | None = None,
) -> AttendanceCache:
    if not student_ids:
        return {}

    query = db.query(Attendance).filter(Attendance.student_id.in_(student_ids))
    if subject_ids:
        query = query.filter(Attendance.subject_id.in_(subject_ids))

    rows = query.all()
    return {(row.student_id, row.subject_id, row.date): row for row in rows}


def _generate_subject_code(name: str, semester: int) -> str:
    prefix = "".join(word[0].upper() for word in name.split()[:3] if word)
=======
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
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    return f"{prefix}{semester:02d}"


def get_or_create_subject(
    db: Session,
    subject_cache: SubjectCache,
<<<<<<< HEAD
    *,
    name: str,
    semester: int | None,
) -> Subject:
    normalized_name = _normalize_subject_name(name)
    if not normalized_name:
        raise ValueError("Subject name is required.")

    candidates = subject_cache.setdefault(normalized_name, [])

    if semester is None:
        if len(candidates) == 1:
            subject = candidates[0]
            logger.info(
                "Semester missing for subject '%s'; reusing existing semester=%s.",
                normalized_name,
                subject.semester,
            )
            return subject
        if len(candidates) > 1:
            known_semesters = sorted({candidate.semester for candidate in candidates})
            raise ValueError(
                f"Subject '{normalized_name}' exists in multiple semesters {known_semesters}; semester is required."
            )

        effective_semester = DEFAULT_SUBJECT_SEMESTER
        logger.warning(
            "Semester missing for new subject '%s'; defaulting to semester=%s.",
            normalized_name,
            effective_semester,
        )
    else:
        effective_semester = semester

    for subject in candidates:
        if subject.semester == effective_semester:
            return subject

    base_code = _generate_subject_code(normalized_name, effective_semester)
    code = base_code
    suffix = 1
    while db.query(Subject.id).filter(Subject.code == code).first():
        code = f"{base_code}{suffix}"
        suffix += 1

    subject = Subject(name=normalized_name, code=code, semester=effective_semester)
    db.add(subject)
    db.flush()
    candidates.append(subject)
    logger.info(
        "Auto-created subject '%s' code=%s semester=%s",
        subject.name,
        subject.code,
        subject.semester,
    )
    return subject


=======
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

>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
def get_or_create_student(
    db: Session,
    student_cache: StudentCache,
    *,
<<<<<<< HEAD
    roll_number: str,
    name: str | None = None,
    email: str | None = None,
    department: str | None = None,
    year: int | None = None,
    section: str | None = None,
    cgpa: float | None = None,
    sgpa: float | None = None,
    teacher_department: str | None = None,
) -> tuple[Student, bool]:
    normalized_roll = _normalize_roll_number(roll_number)
    if normalized_roll in student_cache:
        student = student_cache[normalized_roll]
        changed = False

        if department and student.department != department:
            student.department = department
            changed = True
        if year is not None and student.year != year:
            student.year = year
            changed = True
        if section and student.section != section:
            student.section = section
            changed = True
        if cgpa is not None and student.cgpa != cgpa:
            student.cgpa = cgpa
            changed = True
        if sgpa is not None and student.sgpa != sgpa:
            student.sgpa = sgpa
            changed = True

        user = db.get(User, student.user_id)
        if user and name and user.name != name:
            user.name = name
            changed = True
        if user and email:
            normalized_email = email.strip().lower()
            if user.email != normalized_email:
                user.email = normalized_email
                changed = True

=======
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
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
        if changed:
            db.flush()
        return student, False

<<<<<<< HEAD
    user_name = name.strip() if name else normalized_roll
    user_email = email.strip().lower() if email else f"{normalized_roll}@student.edu"
    student_department = department or teacher_department or "Unknown"
    student_year = year if year is not None else 1
    student_section = section or "UNASSIGNED"

    user = User(
        name=user_name,
=======
    # CREATE
    user_email = email.strip().lower() if email else f"{key}@student.edu"
    user = User(
        name=name.strip(),
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
        email=user_email,
        password=hash_password("Password@123"),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()

    student = Student(
        user_id=user.id,
<<<<<<< HEAD
        roll_number=normalized_roll,
        department=student_department,
        year=student_year,
        section=student_section,
        cgpa=float(cgpa) if cgpa is not None else 0.0,
        sgpa=float(sgpa) if sgpa is not None else 0.0,
=======
        roll_number=key,
        department=department,
        year=year,
        section=section,
        cgpa=cgpa,
        sgpa=sgpa,
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    )
    db.add(student)
    db.flush()

<<<<<<< HEAD
    student_cache[normalized_roll] = student
    logger.info("Created student roll_number=%s", normalized_roll)
    return student, True


def ensure_teacher_link(db: Session, student: Student, teacher: Teacher) -> None:
=======
    student_cache[key] = student
    return student, True


def ensure_teacher_link(
    db: Session,
    student: Student,
    teacher: Teacher,
) -> None:
    """Create TeacherStudent link if it doesn't already exist."""
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
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


<<<<<<< HEAD
def ensure_student_subject_link(db: Session, student: Student, subject: Subject) -> None:
=======
def ensure_student_subject_link(
    db: Session,
    student: Student,
    subject: Subject,
) -> None:
    """Create StudentSubject enrolment link if absent."""
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
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


<<<<<<< HEAD
=======
# ══════════════════════════════════════════════════════════════════════════════
# ACADEMIC RECORD HELPERS  (core of the diff-detection layer)
# ══════════════════════════════════════════════════════════════════════════════

>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
def upsert_academic_record(
    db: Session,
    record_cache: RecordCache,
    *,
    student_id: int,
    subject_id: int,
    semester: int,
<<<<<<< HEAD
    marks: float | None = None,
    attendance_percentage: float | None = None,
    backlogs: int | None = None,
    detained: bool | None = None,
) -> str:
=======
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
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    key = (student_id, subject_id, semester)
    existing = record_cache.get(key)

    if existing is None:
<<<<<<< HEAD
        if marks is None:
            return "skipped"

=======
        # ── INSERT ──────────────────────────────────────────────────────────
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
        record = AcademicRecord(
            student_id=student_id,
            subject_id=subject_id,
            semester=semester,
<<<<<<< HEAD
            marks=round(float(marks), 2),
            attendance_percentage=round(float(attendance_percentage or 0.0), 2),
            backlogs=int(backlogs or 0),
            detained=bool(detained) if detained is not None else False,
=======
            marks=round(marks, 2),
            attendance_percentage=round(attendance_percentage, 2),
            backlogs=backlogs,
            detained=detained,
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
            last_updated_at=datetime.utcnow(),
            updated_by_import=True,
        )
        db.add(record)
        db.flush()
        record_cache[key] = record
        return "created"

<<<<<<< HEAD
    changed = False

    if marks is not None and round(float(existing.marks), 2) != round(float(marks), 2):
        existing.marks = round(float(marks), 2)
        changed = True
    if attendance_percentage is not None and round(float(existing.attendance_percentage), 2) != round(float(attendance_percentage), 2):
        existing.attendance_percentage = round(float(attendance_percentage), 2)
        changed = True
    if backlogs is not None and existing.backlogs != int(backlogs):
        existing.backlogs = int(backlogs)
        changed = True
    if detained is not None and existing.detained != bool(detained):
        existing.detained = bool(detained)
        changed = True

    if not changed:
        return "skipped"

=======
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

>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    existing.last_updated_at = datetime.utcnow()
    existing.updated_by_import = True
    db.flush()
    return "updated"


<<<<<<< HEAD
def upsert_attendance_record(
    db: Session,
    attendance_cache: AttendanceCache,
    *,
    student_id: int,
    subject_id: int,
    attendance_date: date,
    status: AttendanceStatus,
) -> str:
    key = (student_id, subject_id, attendance_date)
    existing = attendance_cache.get(key)

    if existing is None:
        record = Attendance(
            student_id=student_id,
            subject_id=subject_id,
            date=attendance_date,
            status=status,
        )
        db.add(record)
        db.flush()
        attendance_cache[key] = record
        return "created"

    if existing.status == status:
        return "skipped"

    existing.status = status
    db.flush()
    return "updated"


def calculate_attendance_percentage(
    db: Session,
    *,
    student_id: int,
    subject_id: int,
) -> float | None:
    totals = (
        db.query(
            func.count(Attendance.id).label("total"),
            func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
        )
        .filter(
            Attendance.student_id == student_id,
            Attendance.subject_id == subject_id,
        )
        .first()
    )

    if not totals or not totals.total:
        return None
    return round((float(totals.present or 0) * 100.0) / float(totals.total), 2)

=======
# ══════════════════════════════════════════════════════════════════════════════
# SEMESTER RESULT HELPERS
# ══════════════════════════════════════════════════════════════════════════════
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479

def upsert_semester_result(
    db: Session,
    *,
    student_id: int,
    semester: int,
    sgpa: float | None,
    cgpa: float | None,
    backlogs: int | None = None,
) -> None:
<<<<<<< HEAD
=======
    """
    Update or create the SemesterResult for a student.
    Only updates fields if they are provided (not None).
    """
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    if sgpa is None and cgpa is None and backlogs is None:
        return

    existing = (
        db.query(SemesterResult)
<<<<<<< HEAD
        .filter(
            SemesterResult.student_id == student_id,
            SemesterResult.semester == semester,
        )
=======
        .filter(SemesterResult.student_id == student_id, SemesterResult.semester == semester)
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
        .first()
    )

    if not existing:
<<<<<<< HEAD
        record = SemesterResult(
=======
        res = SemesterResult(
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
            student_id=student_id,
            semester=semester,
            sgpa=float(sgpa) if sgpa is not None else 0.0,
            cgpa=float(cgpa) if cgpa is not None else 0.0,
            backlogs=int(backlogs) if backlogs is not None else 0,
        )
<<<<<<< HEAD
        db.add(record)
        db.flush()
        return

    if sgpa is not None:
        existing.sgpa = float(sgpa)
    if cgpa is not None:
        existing.cgpa = float(cgpa)
    if backlogs is not None:
        existing.backlogs = int(backlogs)
    db.flush()


=======
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

>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
def resolve_teacher(
    db: Session,
    current_user: User,
    teacher_id: int | None,
) -> Teacher:
<<<<<<< HEAD
=======
    """
    Determine which Teacher record to associate new students with.
    - TEACHER role → use their own profile.
    - ADMIN with teacher_id → use that specific teacher.
    - ADMIN without teacher_id → pick the first available teacher.
    """
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise ValueError("Teacher profile not found for the current account.")
        return teacher

    teachers = db.query(Teacher).order_by(Teacher.id.asc()).all()
    if not teachers:
        raise ValueError("No teacher profiles exist. Create at least one teacher before importing.")

    if teacher_id is not None:
<<<<<<< HEAD
        teacher = next((row for row in teachers if row.id == teacher_id), None)
        if not teacher:
            raise ValueError(f"teacher_id={teacher_id} does not exist.")
        return teacher
=======
        selected = next((t for t in teachers if t.id == teacher_id), None)
        if not selected:
            raise ValueError(f"teacher_id={teacher_id} does not exist.")
        return selected
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479

    return teachers[0]


<<<<<<< HEAD
=======
# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
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
<<<<<<< HEAD
=======
    """Persist an ImportAudit row after the import finishes."""
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
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
