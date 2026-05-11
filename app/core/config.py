from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Worsyn API"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3001"]

    # Database
    database_url: str = "postgresql+asyncpg://worsyn:worsyn@db:5432/worsyn"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Auth
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
