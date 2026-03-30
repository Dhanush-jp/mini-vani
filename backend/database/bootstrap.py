"""Ensure MySQL database exists before ORM connects to it."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

<<<<<<< HEAD
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
=======
from sqlalchemy import create_engine, text
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
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
<<<<<<< HEAD


def ensure_runtime_schema_compatibility(engine: Engine) -> None:
    """
    Bring older installations up to the minimum schema expected by the ORM.

    This is a narrow compatibility layer for legacy databases where `create_all()`
    cannot add newly introduced columns to existing tables.
    """
    inspector = inspect(engine)
    if not inspector.has_table("students"):
        logger.info("Schema compatibility check skipped: 'students' table does not exist yet.")
        return

    existing_columns = {column["name"].lower() for column in inspector.get_columns("students")}
    statements: list[tuple[str, str]] = []

    if "cgpa" not in existing_columns:
        statements.append(
            (
                "students.cgpa",
                "ALTER TABLE `students` ADD COLUMN `cgpa` FLOAT NOT NULL DEFAULT 0.0",
            )
        )
    if "sgpa" not in existing_columns:
        statements.append(
            (
                "students.sgpa",
                "ALTER TABLE `students` ADD COLUMN `sgpa` FLOAT NOT NULL DEFAULT 0.0",
            )
        )

    if not statements:
        logger.info("Schema compatibility check passed: 'students' table already has cgpa and sgpa.")
        return

    with engine.begin() as connection:
        for column_name, statement in statements:
            logger.warning("Applying runtime schema compatibility fix for %s.", column_name)
            connection.execute(text(statement))

    logger.info(
        "Runtime schema compatibility applied successfully for columns: %s",
        ", ".join(column_name for column_name, _ in statements),
    )
=======
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
