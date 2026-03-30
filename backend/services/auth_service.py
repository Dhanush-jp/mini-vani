from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from auth.security import create_access_token, hash_password, verify_password
from models.entities import Student, Teacher, User, UserRole
from schemas.auth import LoginRequest, RegisterRequest
from database.config import settings

class AuthService:
    @staticmethod
    def authenticate_user(db: Session, payload: LoginRequest) -> Tuple[User, str]:
        user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
        if not user or not verify_password(payload.password, user.password):
            logger.warning(f"Failed login attempt for email: {payload.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )
            
        try:
            token = create_access_token(str(user.id), user.role.value)
            return user, token
        except Exception as e:
            logger.exception(f"Token generation failed for user {user.id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed. Could not generate access token."
            )

    @staticmethod
    def register_user(db: Session, payload: RegisterRequest) -> Tuple[User, str]:
        email_norm = payload.email.lower().strip()
        
        # 1. Existence Check
        if db.query(User).filter(User.email == email_norm).first():
            raise HTTPException(status_code=400, detail="This email is already registered.")

        # 2. Strict Role Validation
        AuthService._validate_role_payload(db, payload)

        try:
            # 3. User Creation
            password_hash = hash_password(payload.password)
            user = User(
                name=payload.name.strip(),
                email=email_norm,
                password=password_hash,
                role=payload.role,
            )
            db.add(user)
            db.flush() # Ensure we have user.id

            # 4. Profile Creation
            if payload.role == UserRole.TEACHER:
                db.add(Teacher(user_id=user.id, department=payload.department.strip()))
            elif payload.role == UserRole.STUDENT:
                db.add(Student(
                    user_id=user.id,
                    roll_number=payload.roll_number.strip(),
                    department=payload.department.strip(),
                    year=payload.year,
                    section=payload.section.strip(),
                ))
            
            db.commit()
            token = create_access_token(str(user.id), user.role.value)
            logger.info(f"New {payload.role} registered: {email_norm}")
            return user, token

        except IntegrityError as e:
            db.rollback()
            logger.warning(f"Registration conflict for {email_norm}: {e}")
            raise HTTPException(status_code=400, detail="Registration failed due to data conflict (e.g. roll number or email taken).")
        except Exception as e:
            db.rollback()
            logger.exception(f"Unexpected error during registration of {email_norm}")
            raise HTTPException(status_code=500, detail="Registration failed. Internal error.")

    @staticmethod
    def _validate_role_payload(db: Session, payload: RegisterRequest):
        if payload.role == UserRole.TEACHER:
            if not payload.department:
                raise HTTPException(status_code=422, detail="Department is required for teachers.")
        elif payload.role == UserRole.STUDENT:
            if not all([payload.department, payload.roll_number, payload.year, payload.section]):
                raise HTTPException(status_code=422, detail="All student profile fields are required.")
            if db.query(Student).filter(Student.roll_number == payload.roll_number.strip()).first():
                raise HTTPException(status_code=400, detail="This roll number is already registered.")

    @staticmethod
    def change_password(db: Session, user: User, old_password: str, new_password: str):
        if not verify_password(old_password, user.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid old password.")
        try:
            user.password = hash_password(new_password)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Password update failed for {user.email}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update password.")
