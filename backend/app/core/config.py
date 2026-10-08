from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Business Defaults (Roadmap D3, D4, D5)
    TIMEZONE: str = "Asia/Manila"
    CURRENCY_CODE: str = "PHP"
    DEFAULT_VAT_RATE: float = 0.12

    # Database
    DATABASE_URL: str = "postgresql+psycopg://erp_app:erp_app_password@localhost:5432/erp_crm"
    MIGRATION_DATABASE_URL: str = (
        "postgresql+psycopg://erp_owner:erp_owner_password@localhost:5432/erp_crm"
    )

    # Security & Auth (Roadmap §4.9)
    SECRET_KEY: str = "dev-secret-key-replace-in-production-min-32-chars-0123456789"
    SESSION_COOKIE_NAME: str = "erp_session"
    CSRF_COOKIE_NAME: str = "csrf_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    SESSION_IDLE_HOURS: int = 8
    SESSION_ABSOLUTE_DAYS: int = 7
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_MINUTES: int = 15

    # Bootstrap Admin (Roadmap V0.1)
    FIRST_SUPERUSER_EMAIL: str = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "AdminPassword123!"
    FIRST_SUPERUSER_NAME: str = "System Administrator"


settings = Settings()
