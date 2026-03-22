from datetime import date, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.session import Base


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LEAVE = "LEAVE"


class ExportType(str, Enum):
    STUDENTS = "STUDENTS"
    SINGLE_STUDENT = "SINGLE_STUDENT"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    teacher = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    student = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    exports = relationship("Export", back_populates="user")


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)

    user = relationship("User", back_populates="teacher")
    teacher_students = relationship("TeacherStudent", back_populates="teacher", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    roll_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(20), nullable=False)

    user = relationship("User", back_populates="student")
    teacher_students = relationship("TeacherStudent", back_populates="student", cascade="all, delete-orphan")
    student_subjects = relationship("StudentSubject", back_populates="student", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="student", cascade="all, delete-orphan")
    attendance = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    semester_results = relationship("SemesterResult", back_populates="student", cascade="all, delete-orphan")
    risk_analysis = relationship("RiskAnalysis", back_populates="student", cascade="all, delete-orphan")


class TeacherStudent(Base):
    __tablename__ = "teacher_students"
    __table_args__ = (UniqueConstraint("teacher_id", "student_id", name="uq_teacher_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)

    teacher = relationship("Teacher", back_populates="teacher_students")
    student = relationship("Student", back_populates="teacher_students")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)

    student_subjects = relationship("StudentSubject", back_populates="subject")
    grades = relationship("Grade", back_populates="subject")
    attendance = relationship("Attendance", back_populates="subject")


class StudentSubject(Base):
    __tablename__ = "student_subjects"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", name="uq_student_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)

    student = relationship("Student", back_populates="student_subjects")
    subject = relationship("Subject", back_populates="student_subjects")


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "semester", name="uq_grade_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    marks: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(4), nullable=False)
    is_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)

    student = relationship("Student", back_populates="grades")
    subject = relationship("Subject", back_populates="grades")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "date", name="uq_attendance_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(SQLEnum(AttendanceStatus), nullable=False)

    student = relationship("Student", back_populates="attendance")
    subject = relationship("Subject", back_populates="attendance")


class SemesterResult(Base):
    __tablename__ = "semester_results"
    __table_args__ = (UniqueConstraint("student_id", "semester", name="uq_semester_result_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    sgpa: Mapped[float] = mapped_column(Float, nullable=False)
    cgpa: Mapped[float] = mapped_column(Float, nullable=False)
    backlogs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    student = relationship("Student", back_populates="semester_results")


class RiskAnalysis(Base):
    __tablename__ = "risk_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, unique=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    prediction_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    suggestions: Mapped[str] = mapped_column(String(1024), nullable=False)

    student = relationship("Student", back_populates="risk_analysis")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[ExportType] = mapped_column(SQLEnum(ExportType), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="exports")
