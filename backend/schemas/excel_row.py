from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional

class ExcelRow(BaseModel):
    name: str = Field("Unknown", description="Student Name")
    email: Optional[EmailStr] = Field(None, description="Unique Email")
    roll_number: str = Field(..., min_length=1)  # STILL REQUIRED for identity
    department: str = Field("General", description="Department Name")
    year: int = Field(1, ge=1, le=4)
    section: str = Field("A", min_length=1)
    semester: int = Field(1, ge=1, le=8)
    subject: str = Field("General", min_length=1)
    marks: float = Field(0.0, ge=0, le=100)
    attendance: float = Field(0.0, ge=0, le=100)
    backlogs: int = Field(0, ge=0)
    detained: bool = Field(False)
    cgpa: Optional[float] = Field(0.0, ge=0, le=10)
    sgpa: Optional[float] = Field(0.0, ge=0, le=10)

    @validator("detained", pre=True)
    def normalize_detained(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            v_low = v.lower().strip()
            return v_low in ("true", "1", "yes", "y", "t", "present", "on")
        return False

    class Config:
        populate_by_name = True
        coerce_numbers_to_str = False
