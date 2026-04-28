from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── General ──
    APP_NAME: str = "MegooBug"
    APP_URL: str = "http://localhost:3000"
    SECRET_KEY: str = "change-me-to-a-random-64-char-string"
    ENVIRONMENT: str = "development"

    # ── Auth ──
    ALLOW_SIGNUP: bool = True
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    INVITE_TOKEN_EXPIRE_HOURS: int = 48
    JWT_ALGORITHM: str = "HS256"

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://megoo:password@postgres:5432/megoobug"

    # ── Redis ──
    REDIS_URL: str = "redis://redis:6379/0"

    # ── SMTP ──
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_TLS: bool = True

    # ── Meilisearch ──
    MEILISEARCH_URL: str = "http://meilisearch:7700"
    MEILISEARCH_MASTER_KEY: str = "change-me-to-a-random-32-char-string"

    # ── Seed Admin ──
    ADMIN_EMAIL: str = "admin@megoobug.local"
    ADMIN_PASSWORD: str = "admin123456"
    ADMIN_NAME: str = "Admin"

    # ── CORS ──
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
