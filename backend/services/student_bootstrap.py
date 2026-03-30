"""Attach default subjects, grades, and attendance to a new student so dashboards are populated."""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.entities import Attendance, AttendanceStatus, Grade, StudentSubject, Subject
from services.grading import compute_grade, recompute_student_metrics


def bootstrap_student_academic_records(db: Session, student_id: int) -> None:
    """
    Idempotent-friendly: adds records only when the student has no grades yet.
    Uses up to 6 subjects from the catalog and light demo marks/attendance.
    """
    existing = db.query(Grade).filter(Grade.student_id == student_id).first()
    if existing:
        return

    subjects = db.query(Subject).order_by(Subject.semester.asc()).limit(6).all()
    if not subjects:
        return

    random.seed(student_id)
    start_day = date.today() - timedelta(days=20)

    for subject in subjects:
        db.add(StudentSubject(student_id=student_id, subject_id=subject.id))
        marks = round(random.uniform(55, 88), 2)
        grade_value, is_pass = compute_grade(marks)
        db.add(
            Grade(
                student_id=student_id,
                subject_id=subject.id,
                semester=subject.semester,
                marks=marks,
                grade=grade_value,
                is_pass=is_pass,
            )
        )
        for day_offset in range(10):
            status = random.choices(
                [AttendanceStatus.PRESENT, AttendanceStatus.ABSENT, AttendanceStatus.LEAVE],
                weights=[80, 15, 5],
                k=1,
            )[0]
            db.add(
                Attendance(
                    student_id=student_id,
                    subject_id=subject.id,
                    date=start_day + timedelta(days=day_offset),
                    status=status,
                )
            )

    db.flush()
    recompute_student_metrics(db, student_id)
