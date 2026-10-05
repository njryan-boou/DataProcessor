from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATAFLOW_", extra="ignore",
        env_file=(str(Path(__file__).resolve().parents[2] / ".env"), ".env"),
    )
    ai_api_key: str = Field(default="", repr=False)
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    max_upload_mb: int = Field(default=20, ge=1, le=200)
    max_rows: int = Field(default=200_000, ge=1)
    max_columns: int = Field(default=200, ge=1)
    max_datasets: int = Field(default=8, ge=1)
    history_limit: int = Field(default=20, ge=1, le=100)
    max_memory_mb: int = Field(default=512, ge=16)
    dataset_ttl_seconds: int = Field(default=3600, ge=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
