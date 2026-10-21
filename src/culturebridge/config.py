from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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
    quiz_repair_attempts: int = Field(default=1, ge=0, le=1)
    maintenance_enabled: bool = False
    maintenance_interval_hours: int = Field(default=24, ge=1, le=168)
    backup_dir: Path = Path("backups")
    backup_keep: int = Field(default=14, ge=1, le=365)
    record_retention_days: int = Field(default=90, ge=1, le=3650)
    retention_enabled: bool = False
    gemini_enabled: bool = True
    heritage_timeout_seconds: int = Field(default=10, ge=1, le=30)
    heritage_cache_hours: int = Field(default=24, ge=1, le=168)
    public_mode: bool = False
    secure_cookies: bool = False
    max_learning_jobs: int = Field(default=3, ge=1, le=16)
    learning_reuse_seconds: int = Field(default=300, ge=0, le=3600)
    requests_per_minute: int = Field(default=30, ge=1, le=120)
    individual_sources_enabled: bool = True
    learning_turn_seconds: int = Field(default=45, ge=5, le=90)
    learning_turn_steps: int = Field(default=6, ge=2, le=8)
    stdict_api_key: SecretStr | None = Field(default=None, validation_alias="STDICT_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
