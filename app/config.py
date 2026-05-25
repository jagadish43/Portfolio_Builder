from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class Settings(BaseSettings):
    app_name: str = "Portfolio Builder"
    app_env: str = "development"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/portfolio_builder"
    )

    session_secret: str = "change-me-for-production"
    csrf_secret: str = "change-me-too"
    root_domain: str = "portfolio.local"
    default_site_scheme: str = "https"
    auto_create_tables: bool = True
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "*.portfolio.local"]
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_personal_access_token: str | None = None

    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None

    vercel_api_token: str | None = None
    vercel_team_id: str | None = None
    vercel_project_id: str | None = None

    analytics_salt: str = "portfolio-analytics"
    pdf_export_engine: str = "reportlab"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
