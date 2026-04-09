from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import select

from auth.security import hash_password
from database.bootstrap import ensure_database_exists, ensure_runtime_schema_compatibility
from database.session import Base, SessionLocal, engine
from models.entities import Attendance, AttendanceStatus, Export, Grade, RiskAnalysis, SemesterResult, Student, StudentSubject, Subject, Teacher, TeacherStudent, User, UserRole
from services.grading import compute_grade, recompute_student_metrics

DEPARTMENTS = ["CSE", "ECE", "EEE", "MECH", "CIVIL"]
SECTIONS = ["A", "B", "C"]
SUBJECT_BLUEPRINTS = [
    ("Mathematics I", "MATH101", 1),
    ("Programming Fundamentals", "CSE101", 1),
    ("Digital Logic", "ECE101", 1),
    ("Data Structures", "CSE201", 2),
    ("Database Systems", "CSE202", 2),
    ("Operating Systems", "CSE301", 3),
]


def ensure_subjects(db):
    """
    Ensure every blueprint subject exists (match by code). Safe to run on a DB that
    already has some subjects — missing rows are inserted without duplicating codes.
    """
    existing_codes = set(db.scalars(select(Subject.code)).all())
    for name, code, semester in SUBJECT_BLUEPRINTS:
        if code in existing_codes:
            continue
        db.add(Subject(name=name, code=code, semester=semester))
    db.flush()
    subjects = db.query(Subject).order_by(Subject.id.asc()).all()
    if not subjects:
        raise RuntimeError("No subjects in database after ensure_subjects — check SUBJECT_BLUEPRINTS and DB connection.")
    return subjects


def reset_seed_entities(db):
    db.query(Export).delete()
    db.query(RiskAnalysis).delete()
    db.query(SemesterResult).delete()
    db.query(Attendance).delete()
    db.query(Grade).delete()
    db.query(StudentSubject).delete()
    db.query(TeacherStudent).delete()
    db.query(Student).delete()
    db.query(Teacher).delete()
    db.query(User).filter(User.email.like("%@college.com")).delete(synchronize_session=False)


def create_user(db, name: str, email: str, role: UserRole, password: str = "Password@123") -> User:
    user = User(name=name, email=email, password=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def seed():
    ensure_database_exists()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema_compatibility(engine)

    db = SessionLocal()
    random.seed(42)
    try:
        reset_seed_entities(db)
        subjects = ensure_subjects(db)

        admin_user = create_user(db, "Admin", "admin@college.com", UserRole.ADMIN)
        _ = admin_user

        teachers: list[Teacher] = []
        for index in range(1, 11):
            user = create_user(db, f"Teacher {index}", f"teacher{index}@college.com", UserRole.TEACHER)
            teacher = Teacher(user_id=user.id, department=DEPARTMENTS[(index - 1) % len(DEPARTMENTS)])
            db.add(teacher)
            db.flush()
            teachers.append(teacher)

        student_counter = 1
        start_day = date.today() - timedelta(days=30)
        for teacher in teachers:
            for _ in range(60):
                user = create_user(db, f"Student {student_counter}", f"student{student_counter}@college.com", UserRole.STUDENT)
                department = teacher.department
                year = random.randint(1, 4)
                section = random.choice(SECTIONS)
                student = Student(
                    user_id=user.id,
                    roll_number=f"ROLL{student_counter:04d}",
                    department=department,
                    year=year,
                    section=section,
                )
                db.add(student)
                db.flush()
                db.add(TeacherStudent(teacher_id=teacher.id, student_id=student.id))

                subject_count = random.randint(5, 6)
                selected_subjects = random.sample(subjects, subject_count)
                for subject in selected_subjects:
                    db.add(StudentSubject(student_id=student.id, subject_id=subject.id))
                    marks = round(random.uniform(35, 96), 2)
                    grade_value, is_pass = compute_grade(marks)
                    db.add(
                        Grade(
                            student_id=student.id,
                            subject_id=subject.id,
                            semester=subject.semester,
                            marks=marks,
                            grade=grade_value,
                            is_pass=is_pass,
                        )
                    )

                    for day_offset in range(12):
                        status = random.choices(
                            [AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.LEAVE],
                            weights=[78, 17, 5],
                            k=1,
                        )[0]
                        db.add(
                            Attendance(
                                student_id=student.id,
                                subject_id=subject.id,
                                date=start_day + timedelta(days=day_offset),
                                status=status,
                            )
                        )

                db.flush()
                recompute_student_metrics(db, student.id)
                student_counter += 1

        db.commit()
        print(f"Seed completed: 1 admin, 10 teachers, 600 students, {len(subjects)} subject(s) in catalog.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
