import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from database.bootstrap import ensure_database_exists
from database.config import settings
from database.session import Base, engine
from routers import admin, auth, exports, student, teacher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
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


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    """Preserve correct status codes (generic Exception handler would turn these into 500)."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError):
    logger.exception("Database error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Database operation failed."})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception):
    logger.exception("Unhandled server error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(teacher.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(student.router, prefix=settings.api_v1_prefix)
app.include_router(student.students_alias_router, prefix=settings.api_v1_prefix)
app.include_router(exports.router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
