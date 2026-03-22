from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from database.config import settings


def hash_password(password: str) -> str:
    """
    Hash password with bcrypt (native library — avoids passlib/bcrypt 4.x incompatibilities).
    Bcrypt truncates at 72 bytes; we reject longer passwords explicitly.
    """
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")
    pw = password.encode("utf-8")
    if len(pw) > 72:
        raise ValueError("Password cannot be longer than 72 bytes (bcrypt limit).")
    if len(pw) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw, salt).decode("ascii")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    # python-jose expects numeric `exp` (Unix timestamp), not a datetime object
    payload = {
        "sub": subject,
        "role": role,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
