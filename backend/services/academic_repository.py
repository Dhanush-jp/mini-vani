from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from auth.security import hash_password
from models.entities import (
    AcademicRecord,
    Attendance,
    AttendanceStatus,
    ImportAudit,
    ImportStatus,
    SemesterResult,
    Student,
    StudentSubject,
    Subject,
    Teacher,
    TeacherStudent,
    User,
    UserRole,
)


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
    return f"{prefix}{semester:02d}"


def get_or_create_subject(
    db: Session,
    subject_cache: SubjectCache,
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


def get_or_create_student(
    db: Session,
    student_cache: StudentCache,
    *,
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

        if changed:
            db.flush()
        return student, False

    user_name = name.strip() if name else normalized_roll
    user_email = email.strip().lower() if email else f"{normalized_roll}@student.edu"
    student_department = department or teacher_department or "Unknown"
    student_year = year if year is not None else 1
    student_section = section or "UNASSIGNED"

    user = User(
        name=user_name,
        email=user_email,
        password=hash_password("Password@123"),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()

    student = Student(
        user_id=user.id,
        roll_number=normalized_roll,
        department=student_department,
        year=student_year,
        section=student_section,
        cgpa=float(cgpa) if cgpa is not None else 0.0,
        sgpa=float(sgpa) if sgpa is not None else 0.0,
    )
    db.add(student)
    db.flush()

    student_cache[normalized_roll] = student
    logger.info("Created student roll_number=%s", normalized_roll)
    return student, True


def ensure_teacher_link(db: Session, student: Student, teacher: Teacher) -> None:
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


def ensure_student_subject_link(db: Session, student: Student, subject: Subject) -> None:
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


def upsert_academic_record(
    db: Session,
    record_cache: RecordCache,
    *,
    student_id: int,
    subject_id: int,
    semester: int,
    marks: float | None = None,
    attendance_percentage: float | None = None,
    backlogs: int | None = None,
    detained: bool | None = None,
) -> str:
    key = (student_id, subject_id, semester)
    existing = record_cache.get(key)

    if existing is None:
        if marks is None:
            return "skipped"

        record = AcademicRecord(
            student_id=student_id,
            subject_id=subject_id,
            semester=semester,
            marks=round(float(marks), 2),
            attendance_percentage=round(float(attendance_percentage or 0.0), 2),
            backlogs=int(backlogs or 0),
            detained=bool(detained) if detained is not None else False,
            last_updated_at=datetime.utcnow(),
            updated_by_import=True,
        )
        db.add(record)
        db.flush()
        record_cache[key] = record
        return "created"

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

    existing.last_updated_at = datetime.utcnow()
    existing.updated_by_import = True
    db.flush()
    return "updated"


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


def upsert_semester_result(
    db: Session,
    *,
    student_id: int,
    semester: int,
    sgpa: float | None,
    cgpa: float | None,
    backlogs: int | None = None,
) -> None:
    if sgpa is None and cgpa is None and backlogs is None:
        return

    existing = (
        db.query(SemesterResult)
        .filter(
            SemesterResult.student_id == student_id,
            SemesterResult.semester == semester,
        )
        .first()
    )

    if not existing:
        record = SemesterResult(
            student_id=student_id,
            semester=semester,
            sgpa=float(sgpa) if sgpa is not None else 0.0,
            cgpa=float(cgpa) if cgpa is not None else 0.0,
            backlogs=int(backlogs) if backlogs is not None else 0,
        )
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


def resolve_teacher(
    db: Session,
    current_user: User,
    teacher_id: int | None,
) -> Teacher:
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise ValueError("Teacher profile not found for the current account.")
        return teacher

    teachers = db.query(Teacher).order_by(Teacher.id.asc()).all()
    if not teachers:
        raise ValueError("No teacher profiles exist. Create at least one teacher before importing.")

    if teacher_id is not None:
        teacher = next((row for row in teachers if row.id == teacher_id), None)
        if not teacher:
            raise ValueError(f"teacher_id={teacher_id} does not exist.")
        return teacher

    return teachers[0]


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
