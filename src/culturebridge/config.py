from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CULTUREBRIDGE_",
        extra="ignore",
    )

    app_name: str = "CultureBridge"
    app_version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8080
    db_path: Path = Path("data/culturebridge.db")
    storage_secret: str = "culturebridge-local-development"
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    gemini_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    quiz_timeout_ms: int = Field(default=30000, ge=1000, le=60000)
    gemini_enabled: bool = True
    heritage_timeout_seconds: int = Field(default=10, ge=1, le=30)
    heritage_cache_hours: int = Field(default=24, ge=1, le=168)


@lru_cache
def get_settings() -> Settings:
    return Settings()
