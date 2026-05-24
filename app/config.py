from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


class Settings(BaseSettings):
    app_name: str = "Portfolio Builder"
    app_env: str = "development"
    debug: bool = False
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/portfolio_builder"
    )
    session_secret: str = "change-me-for-production"
    root_domain: str = "portfolio.local"
    default_site_scheme: str = "https"
    auto_create_tables: bool = True
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "*.portfolio.local"]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
