import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from database.bootstrap import ensure_database_exists, ensure_runtime_schema_compatibility
from database.config import settings
from database.session import Base, engine
from core.errors import global_exception_handler, validation_exception_handler, sqlalchemy_exception_handler
from core.logging_config import setup_logging
from routers import admin, auth, exports, student, teacher, upload, issues, subjects, import_routes

setup_logging()
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure DB exists and create ORM tables. Shutdown: log only."""
    logger.info("Application starting…")
    try:
        ensure_database_exists()
    except Exception as exc:
        logger.exception("Database bootstrap failed (check DB_HOST, credentials, MySQL running): %s", exc)
        raise
    try:
        Base.metadata.create_all(bind=engine)
        ensure_runtime_schema_compatibility(engine)
    except SQLAlchemyError as exc:
        logger.exception("Failed to create/verify database tables: %s", exc)
        raise
    logger.info("Startup complete. API prefix: %s", settings.api_v1_prefix)
    yield
    logger.info("Application shutdown.")


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# CORS must wrap the whole app (register before routers; last registered = outermost in Starlette).
# Browsers may use http://127.0.0.1:5173, http://localhost:5173, or http://[::1]:5173 — include all.
if settings.cors_allow_all:
    logger.warning("CORS_ALLOW_ALL=true: allowing all origins (credentials disabled). Dev only.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
else:
    logger.info("CORS allow_origins: %s", settings.cors_origin_list)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )


app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(HTTPException, lambda r, e: JSONResponse(
    status_code=e.status_code, 
    content={"success": False, "message": e.detail, "data": None, "errors": []}
))


app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(teacher.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(student.router, prefix=settings.api_v1_prefix)
app.include_router(student.students_alias_router, prefix=settings.api_v1_prefix)
app.include_router(exports.router, prefix=settings.api_v1_prefix)
app.include_router(upload.router, prefix=settings.api_v1_prefix)
app.include_router(issues.router, prefix=settings.api_v1_prefix)
app.include_router(subjects.router, prefix=settings.api_v1_prefix)
app.include_router(import_routes.router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health():
    return {"success": True, "message": "Backend is online", "data": {"status": "ok"}}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
