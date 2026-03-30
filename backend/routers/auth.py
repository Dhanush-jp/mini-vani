from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from auth.deps import require_roles
from database.session import get_db
from models.entities import User, UserRole
from schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse
from schemas.api_response import StandardResponse
from services.auth_service import AuthService
from core.responses import success_response

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=StandardResponse[RegisterResponse], status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user (Teacher or Student) and return an access token."""
    user, token = AuthService.register_user(db, payload)
    data = RegisterResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        message="Registration successful"
    )
    return success_response(data, "Account created successfully.")

@router.post("/login", response_model=StandardResponse[TokenResponse])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return an access token."""
    user, token = AuthService.authenticate_user(db, payload)
    data = TokenResponse(access_token=token, user_id=user.id, role=user.role)
    return success_response(data, f"Welcome back, {user.name}.")

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.put("/change-password", response_model=StandardResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TEACHER, UserRole.STUDENT)),
    db: Session = Depends(get_db)
):
    """Securely change user's password."""
    AuthService.change_password(db, current_user, payload.old_password, payload.new_password)
    return success_response(message="Password changed successfully.")
