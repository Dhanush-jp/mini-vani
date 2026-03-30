from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    roll_number: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    marks: Mapped[list["Mark"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    attendance_records: Mapped[list["Attendance"]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    marks: Mapped[list["Mark"]] = relationship(back_populates="subject", cascade="all, delete-orphan")
    attendance_records: Mapped[list["Attendance"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_marks_student_subject"),
        CheckConstraint("marks >= 0", name="marks_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    marks: Mapped[float] = mapped_column(Float, nullable=False)

    student: Mapped[Student] = relationship(back_populates="marks")
    subject: Mapped[Subject] = relationship(back_populates="marks")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "date", name="uq_attendance_student_subject_date"),
        CheckConstraint("(status IS NOT NULL) OR (percentage IS NOT NULL)", name="status_or_percentage_present"),
        CheckConstraint("(percentage IS NULL) OR (percentage >= 0 AND percentage <= 100)", name="percentage_between_zero_and_hundred"),
        Index(
            "ux_attendance_student_subject_null_date",
            "student_id",
            "subject_id",
            unique=True,
            postgresql_where=text("date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[AttendanceStatus | None] = mapped_column(
        SqlEnum(AttendanceStatus, name="attendance_status"),
        nullable=True,
    )
    percentage: Mapped[float | None] = mapped_column(Float, nullable=True)

    student: Mapped[Student] = relationship(back_populates="attendance_records")
    subject: Mapped[Subject] = relationship(back_populates="attendance_records")
