from pydantic import BaseModel, EmailStr, Field, field_validator

from models.entities import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    department: str | None = Field(default=None, max_length=120)
    roll_number: str | None = Field(default=None, max_length=32)
    year: int | None = Field(default=None, ge=1, le=8)
    section: str | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be blank.")
        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: UserRole


class RegisterResponse(TokenResponse):
    """Same as login token payload plus a human-readable success message."""

    message: str = "User registered successfully"
