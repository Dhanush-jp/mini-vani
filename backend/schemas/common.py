from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

from models.entities import AttendanceStatus


class StudentFilter(BaseModel):
    semester: int | None = Field(default=None, ge=1, le=12)
    subject_id: int | None = Field(default=None, gt=0)
    attendance_min: float | None = Field(default=None, ge=0, le=100)
    attendance_max: float | None = Field(default=None, ge=0, le=100)
    cgpa_min: float | None = Field(default=None, ge=0, le=10)
    cgpa_max: float | None = Field(default=None, ge=0, le=10)
    risk_level: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH)$")
    is_pass: bool | None = None
    student_id: int | None = Field(default=None, gt=0)
    department: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1, le=8)
    section: str | None = Field(default=None, max_length=20)
    search: str | None = Field(default=None, max_length=255)


class StudentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    roll_number: str = Field(min_length=1, max_length=32)
    department: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1, le=8)
    section: str = Field(min_length=1, max_length=20)
    teacher_id: int | None = Field(default=None, gt=0)

    @field_validator("name", "roll_number", "department", "section")
    @classmethod
    def strip_string(cls, value: str) -> str:
        return value.strip()


class TeacherOption(BaseModel):
    id: int
    name: str
    email: EmailStr
    department: str


class SubjectOption(BaseModel):
    id: int
    name: str
    code: str
    semester: int


class StudentSubjectAssign(BaseModel):
    student_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)


class StudentListItem(BaseModel):
    id: int
    user_id: int
    teacher_id: int | None = None
    name: str
    email: EmailStr
    roll_number: str
    department: str
    year: int
    section: str
    sgpa: float | None = None
    cgpa: float | None = None
    backlogs: int = 0
    attendance_pct: float = 0
    risk_score: float | None = None
    risk_level: str | None = None


class StudentListResponse(BaseModel):
    items: list[StudentListItem]
    total: int


class StudentOverview(BaseModel):
    id: int
    user_id: int
    teacher_id: int | None = None
    name: str
    email: EmailStr
    roll_number: str
    department: str
    year: int
    section: str


class DashboardSummary(BaseModel):
    total_students: int
    avg_cgpa: float
    avg_attendance: float
    high_risk_count: int


class StudentManagementBootstrap(BaseModel):
    summary: DashboardSummary
    students: StudentListResponse
    teachers: list[TeacherOption]
    subjects: list[SubjectOption]


class AttendanceUpsert(BaseModel):
    student_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    date: date
    status: AttendanceStatus


class GradeUpsert(BaseModel):
    student_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    semester: int = Field(ge=1, le=12)
    marks: float = Field(ge=0, le=100)


class SemesterResultUpsert(BaseModel):
    student_id: int = Field(gt=0)
    semester: int = Field(ge=1, le=12)
    sgpa: float = Field(ge=0, le=10)
    cgpa: float = Field(ge=0, le=10)
    backlogs: int = Field(ge=0, le=40)


class RiskResponse(BaseModel):
    student_id: int
    risk_score: float
    prediction_date: datetime
    suggestions: str


class AttendanceHistoryItem(BaseModel):
    id: int
    student_id: int
    subject_id: int
    subject_name: str
    date: date
    status: AttendanceStatus


class ResultItem(BaseModel):
    id: int
    student_id: int
    subject_id: int
    subject_name: str
    subject_code: str
    semester: int
    marks: float
    grade: str
    is_pass: bool


class StudentRecordResponse(BaseModel):
    student: StudentOverview
    trends: list[dict]
    backlogs: list[dict]
    marks: list[ResultItem]
    attendance: list[dict]
    pass_fail_ratio: dict
    risk: dict

class SubjectCreate(BaseModel):
    subject_id: int | None = Field(default=None, gt=0)
    subject_name: str | None = Field(default=None, min_length=1)
    marks: float = Field(ge=0, le=100)
    attendance_percentage: float = Field(ge=0, le=100)
    semester: int = Field(default=1, ge=1, le=12)
