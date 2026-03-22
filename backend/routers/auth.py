import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth.security import create_access_token, hash_password, verify_password
from database.config import settings
from database.session import get_db
from models.entities import Student, Teacher, User, UserRole
from services.student_bootstrap import bootstrap_student_academic_records
from schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _integrity_error_detail(exc: IntegrityError) -> str:
    """Map MySQL / SQLAlchemy integrity errors to safe client messages."""
    msg = ""
    if exc.orig is not None:
        msg = str(exc.orig)
    if not msg:
        msg = str(exc)
    lower = msg.lower()
    if "users.email" in lower or ("duplicate" in lower and "email" in lower):
        return "This email is already registered."
    if "roll_number" in lower or "students.roll" in lower or ("duplicate" in lower and "roll" in lower):
        return "This roll number is already registered."
    return "Registration conflicts with existing data (duplicate or invalid reference)."


def _validate_role_payload(payload: RegisterRequest) -> None:
    """Raise HTTPException before any write if role-specific data is invalid."""
    if payload.role == UserRole.TEACHER:
        if not payload.department or not str(payload.department).strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Department is required for teacher registration.",
            )
    elif payload.role == UserRole.STUDENT:
        missing = []
        if not payload.department or not str(payload.department).strip():
            missing.append("department")
        if not payload.roll_number or not str(payload.roll_number).strip():
            missing.append("roll_number")
        if payload.year is None:
            missing.append("year")
        if not payload.section or not str(payload.section).strip():
            missing.append("section")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required fields for student: {', '.join(missing)}.",
            )
        roll = str(payload.roll_number).strip()
        if len(roll) > 32:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Roll number must be at most 32 characters.",
            )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a user and optional teacher/student profile. Returns JWT + success message.
    Duplicate email / roll number → 400 with clear detail (not 500).
    """
    email_norm = payload.email.lower().strip()
    logger.info("Register attempt: email=%s role=%s", email_norm, payload.role)

    existing_user = db.query(User).filter(User.email == email_norm).first()
    if existing_user:
        logger.warning("Register rejected: duplicate email %s", email_norm)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered.",
        )

    _validate_role_payload(payload)

    if payload.role == UserRole.STUDENT:
        roll = str(payload.roll_number).strip()
        roll_taken = db.query(Student).filter(Student.roll_number == roll).first()
        if roll_taken:
            logger.warning("Register rejected: duplicate roll_number %s", roll)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This roll number is already registered.",
            )

    try:
        password_hash = hash_password(payload.password)
    except (ValueError, TypeError) as exc:
        logger.warning("Password hashing validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error hashing password: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process password." if not settings.debug else str(exc),
        ) from exc

    user = User(
        name=payload.name.strip(),
        email=email_norm,
        password=password_hash,
        role=payload.role,
    )
    db.add(user)

    try:
        db.flush()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Flush user failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating user." if not settings.debug else str(exc),
        ) from exc

    try:
        if payload.role == UserRole.TEACHER:
            db.add(Teacher(user_id=user.id, department=payload.department.strip()))
        elif payload.role == UserRole.STUDENT:
            st = Student(
                user_id=user.id,
                roll_number=str(payload.roll_number).strip(),
                department=payload.department.strip(),
                year=int(payload.year),
                section=payload.section.strip(),
            )
            db.add(st)
            db.flush()
            bootstrap_student_academic_records(db, st.id)
        # ADMIN: user row only

        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        detail = _integrity_error_detail(exc)
        logger.warning("Register integrity error: %s -> %s", exc, detail)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Register commit failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to a database error."
            if not settings.debug
            else f"Database error: {exc}",
        ) from exc

    try:
        token = create_access_token(str(user.id), user.role.value)
    except Exception as exc:
        logger.exception("JWT creation failed after successful registration user_id=%s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account created but login token could not be issued."
            if not settings.debug
            else str(exc),
        ) from exc

    logger.info("User registered successfully: id=%s email=%s role=%s", user.id, email_norm, user.role)
    return RegisterResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        message="User registered successfully",
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    try:
        token = create_access_token(str(user.id), user.role.value)
    except Exception as exc:
        logger.exception("JWT creation failed for login user_id=%s: %s", user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not issue token." if not settings.debug else str(exc),
        ) from exc
    return TokenResponse(access_token=token, user_id=user.id, role=user.role)
