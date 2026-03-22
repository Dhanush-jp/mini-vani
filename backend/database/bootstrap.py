"""Ensure MySQL database exists before ORM connects to it."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from database.config import settings

logger = logging.getLogger(__name__)

# MySQL unquoted identifier: letters, digits, underscore only (prevents SQL injection in CREATE DATABASE)
_DB_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def ensure_database_exists() -> None:
    """
    Connect to the MySQL server (no default database) and create DB_NAME if missing.

    Raises:
        ValueError: If DB_NAME is not a safe identifier.
        OperationalError: If the server is unreachable or credentials are invalid.
    """
    db_name = settings.db_name.strip()
    if not db_name:
        raise ValueError("DB_NAME must be set and non-empty.")
    if not _DB_NAME_PATTERN.fullmatch(db_name):
        raise ValueError(
            "DB_NAME must contain only ASCII letters, digits, and underscores "
            "(safe MySQL identifier; avoids injection in CREATE DATABASE)."
        )

    user = quote_plus(settings.db_user)
    password = quote_plus(settings.db_password)
    server_uri = (
        f"mysql+pymysql://{user}:{password}"
        f"@{settings.db_host}:{settings.db_port}/"
    )

    engine = create_engine(
        server_uri,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
        logger.info("Database '%s' is available (created if it did not exist).", db_name)
    except OperationalError as exc:
        logger.exception(
            "Cannot reach MySQL or login failed while ensuring database exists: %s",
            exc,
        )
        raise
    except SQLAlchemyError as exc:
        logger.exception("Unexpected database error while ensuring database exists: %s", exc)
        raise
    finally:
        engine.dispose()
