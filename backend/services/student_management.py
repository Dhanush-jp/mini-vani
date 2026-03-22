from __future__ import annotations

from sqlalchemy import and_, case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.security import hash_password
from fastapi import HTTPException, status
from models.entities import Attendance, AttendanceStatus, Grade, RiskAnalysis, SemesterResult, Student, StudentSubject, Subject, Teacher, TeacherStudent, User, UserRole
from schemas.common import DashboardSummary, StudentCreate, StudentFilter, StudentListItem, StudentListResponse, StudentOverview, SubjectOption, TeacherOption
from services.access import get_teacher_or_404
from services.analytics import allowed_student_scope, build_student_dashboard, resolve_risk_level


def _latest_results_subquery(db: Session):
    return (
        db.query(
            SemesterResult.student_id.label("student_id"),
            func.max(SemesterResult.semester).label("latest_semester"),
        )
        .group_by(SemesterResult.student_id)
        .subquery()
    )


def _attendance_subquery(db: Session):
    return (
        db.query(
            Attendance.student_id.label("student_id"),
            func.round(
                func.sum(case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)) * 100.0 / func.count(Attendance.id),
                2,
            ).label("attendance_pct"),
        )
        .group_by(Attendance.student_id)
        .subquery()
    )


def _teacher_assignment_subquery(db: Session):
    return (
        db.query(
            TeacherStudent.student_id.label("student_id"),
            func.min(TeacherStudent.teacher_id).label("teacher_id"),
        )
        .group_by(TeacherStudent.student_id)
        .subquery()
    )


def _base_students_query(db: Session, current_user: User, filters: StudentFilter | None = None):
    filters = filters or StudentFilter()
    scope = allowed_student_scope(db, current_user).subquery()
    latest_results = _latest_results_subquery(db)
    attendance_stats = _attendance_subquery(db)
    teacher_assignments = _teacher_assignment_subquery(db)

    query = (
        db.query(
            Student.id.label("id"),
            Student.user_id.label("user_id"),
            User.name.label("name"),
            User.email.label("email"),
            Student.roll_number.label("roll_number"),
            Student.department.label("department"),
            Student.year.label("year"),
            Student.section.label("section"),
            teacher_assignments.c.teacher_id.label("teacher_id"),
            SemesterResult.sgpa.label("sgpa"),
            SemesterResult.cgpa.label("cgpa"),
            SemesterResult.backlogs.label("backlogs"),
            attendance_stats.c.attendance_pct.label("attendance_pct"),
            RiskAnalysis.risk_score.label("risk_score"),
            RiskAnalysis.suggestions.label("risk_suggestions"),
        )
        .join(scope, Student.id == scope.c.id)
        .join(User, User.id == Student.user_id)
        .outerjoin(teacher_assignments, teacher_assignments.c.student_id == Student.id)
        .outerjoin(
            latest_results,
            latest_results.c.student_id == Student.id,
        )
        .outerjoin(
            SemesterResult,
            and_(
                SemesterResult.student_id == Student.id,
                SemesterResult.semester == latest_results.c.latest_semester,
            ),
        )
        .outerjoin(attendance_stats, attendance_stats.c.student_id == Student.id)
        .outerjoin(RiskAnalysis, RiskAnalysis.student_id == Student.id)
    )

    if filters.department:
        query = query.filter(Student.department == filters.department.strip())
    if filters.year is not None:
        query = query.filter(Student.year == filters.year)
    if filters.section:
        query = query.filter(Student.section == filters.section.strip())
    if filters.search:
        needle = f"%{filters.search.strip()}%"
        query = query.filter(or_(User.name.ilike(needle), User.email.ilike(needle), Student.roll_number.ilike(needle)))
    if filters.student_id is not None:
        query = query.filter(Student.id == filters.student_id)
    if filters.cgpa_min is not None:
        query = query.filter(SemesterResult.cgpa >= filters.cgpa_min)
    if filters.cgpa_max is not None:
        query = query.filter(SemesterResult.cgpa <= filters.cgpa_max)
    if filters.risk_level is not None:
        if filters.risk_level == "LOW":
            query = query.filter(RiskAnalysis.risk_score < 4)
        elif filters.risk_level == "MEDIUM":
            query = query.filter(RiskAnalysis.risk_score.between(4, 7))
        else:
            query = query.filter(RiskAnalysis.risk_score > 7)
    if filters.attendance_min is not None:
        query = query.filter(func.coalesce(attendance_stats.c.attendance_pct, 0) >= filters.attendance_min)
    if filters.attendance_max is not None:
        query = query.filter(func.coalesce(attendance_stats.c.attendance_pct, 0) <= filters.attendance_max)

    return query


def _student_item_from_row(row) -> StudentListItem:
    risk_score = float(row.risk_score) if row.risk_score is not None else None
    return StudentListItem(
        id=row.id,
        user_id=row.user_id,
        teacher_id=row.teacher_id,
        name=row.name,
        email=row.email,
        roll_number=row.roll_number,
        department=row.department,
        year=row.year,
        section=row.section,
        sgpa=float(row.sgpa) if row.sgpa is not None else None,
        cgpa=float(row.cgpa) if row.cgpa is not None else None,
        backlogs=int(row.backlogs or 0),
        attendance_pct=float(row.attendance_pct or 0),
        risk_score=risk_score,
        risk_level=resolve_risk_level(risk_score),
    )


def list_students(db: Session, current_user: User, filters: StudentFilter | None = None) -> StudentListResponse:
    rows = _base_students_query(db, current_user, filters).order_by(User.name.asc()).all()
    items = [_student_item_from_row(row) for row in rows]
    return StudentListResponse(items=items, total=len(items))


def build_dashboard_summary(db: Session, current_user: User, filters: StudentFilter | None = None) -> DashboardSummary:
    students = list_students(db, current_user, filters).items
    total = len(students)
    if not total:
        return DashboardSummary(total_students=0, avg_cgpa=0, avg_attendance=0, high_risk_count=0)

    cgpas = [student.cgpa for student in students if student.cgpa is not None]
    attendance = [student.attendance_pct for student in students]
    high_risk_count = sum(1 for student in students if student.risk_level == "HIGH")
    return DashboardSummary(
        total_students=total,
        avg_cgpa=round(sum(cgpas) / len(cgpas), 2) if cgpas else 0,
        avg_attendance=round(sum(attendance) / len(attendance), 2) if attendance else 0,
        high_risk_count=high_risk_count,
    )


def list_teachers(db: Session) -> list[TeacherOption]:
    rows = (
        db.query(Teacher.id, Teacher.department, User.name, User.email)
        .join(User, User.id == Teacher.user_id)
        .order_by(User.name.asc())
        .all()
    )
    return [TeacherOption(id=row.id, name=row.name, email=row.email, department=row.department) for row in rows]


def list_subjects(db: Session) -> list[SubjectOption]:
    rows = db.query(Subject).order_by(Subject.semester.asc(), Subject.name.asc()).all()
    return [SubjectOption(id=row.id, name=row.name, code=row.code, semester=row.semester) for row in rows]


def list_student_subjects(db: Session, student_id: int) -> list[SubjectOption]:
    rows = (
        db.query(Subject)
        .join(StudentSubject, StudentSubject.subject_id == Subject.id)
        .filter(StudentSubject.student_id == student_id)
        .order_by(Subject.semester.asc(), Subject.name.asc())
        .all()
    )
    return [SubjectOption(id=row.id, name=row.name, code=row.code, semester=row.semester) for row in rows]


def assign_subject_to_student(db: Session, student_id: int, subject_id: int) -> None:
    exists = (
        db.query(StudentSubject)
        .filter(StudentSubject.student_id == student_id, StudentSubject.subject_id == subject_id)
        .first()
    )
    if exists:
        return
    if not db.query(Subject).filter(Subject.id == subject_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    db.add(StudentSubject(student_id=student_id, subject_id=subject_id))


def create_student(db: Session, current_user: User, payload: StudentCreate) -> StudentOverview:
    if current_user.role == UserRole.TEACHER:
        teacher = get_teacher_or_404(db, current_user.id)
        teacher_id = teacher.id
    elif current_user.role == UserRole.ADMIN:
        teacher_id = payload.teacher_id
        if teacher_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Teacher is required for admin-created students.")
        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found.")
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin or teacher can create students.")

    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This email is already registered.")
    if db.query(Student).filter(Student.roll_number == payload.roll_number).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This roll number is already registered.")

    user = User(
        name=payload.name,
        email=email,
        password=hash_password(payload.password),
        role=UserRole.STUDENT,
    )
    student = Student(
        user=user,
        roll_number=payload.roll_number,
        department=payload.department,
        year=payload.year,
        section=payload.section,
    )
    db.add(user)
    db.add(student)

    try:
        db.flush()
        db.add(TeacherStudent(teacher_id=teacher.id, student_id=student.id))
        for subject in db.query(Subject).order_by(Subject.semester.asc()).limit(6).all():
            db.add(StudentSubject(student_id=student.id, subject_id=subject.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not create student because data already exists or references are invalid.") from exc

    return StudentOverview(
        id=student.id,
        user_id=user.id,
        teacher_id=teacher.id,
        name=user.name,
        email=user.email,
        roll_number=student.roll_number,
        department=student.department,
        year=student.year,
        section=student.section,
    )


def get_student_record(db: Session, current_user: User, student_id: int) -> dict:
    base = (
        _base_students_query(db, current_user, StudentFilter(student_id=student_id))
        .order_by(User.name.asc())
        .first()
    )
    if not base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    student = StudentOverview(
        id=base.id,
        user_id=base.user_id,
        teacher_id=base.teacher_id,
        name=base.name,
        email=base.email,
        roll_number=base.roll_number,
        department=base.department,
        year=base.year,
        section=base.section,
    )
    dashboard = build_student_dashboard(db, student_id)
    return {"student": student, "subjects": list_student_subjects(db, student_id), **dashboard}
