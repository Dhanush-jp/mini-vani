from pathlib import Path
from urllib.parse import quote_plus

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env next to backend package (works even if cwd is not `backend/`)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "AI-Powered Student Intelligence System"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
<<<<<<< HEAD
    db_password: str = "root"
=======
    db_password: str = "bhavani68"
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    db_name: str = "student_intelligence"

    secret_key: str = "change_me_in_env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120

    ml_service_url: str = "http://127.0.0.1:8001"
<<<<<<< HEAD
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_endpoint: str = "https://api.groq.com/openai/v1/chat/completions"
    groq_timeout_seconds: int = 45
=======
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479

    # Comma-separated list, e.g. "http://localhost:5173,http://127.0.0.1:5173"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://[::1]:5173"
    )
    # DEV ONLY: if true, allow any origin (credentials disabled — browser requirement)
    cors_allow_all: bool = False

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "dev"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return value

    @property
    def sqlalchemy_database_uri(self) -> str:
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        parts = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return parts or ["http://localhost:5173"]


settings = Settings()
