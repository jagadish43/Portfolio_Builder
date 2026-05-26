from contextlib import asynccontextmanager

from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router as api_router
from app.config import STATIC_DIR, get_settings
from app.database import Base, engine
from app.public.views import router as public_router
from starlette.middleware.trustedhost import TrustedHostMiddleware


settings = get_settings()


def _ensure_table_columns(table_name: str, required_columns: Mapping[str, str]) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if table_name not in existing_tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )


def _ensure_legacy_schema_compatibility() -> None:
    _ensure_table_columns(
        "users",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        "portfolios",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "section_config": "TEXT NOT NULL DEFAULT '{}'",
            "section_order": "TEXT NOT NULL DEFAULT '[\"about\",\"skills\",\"education\",\"projects\",\"experience\",\"certificates\",\"contact\"]'",
            "theme_config": "TEXT NOT NULL DEFAULT '{}'",
            "education_text": "TEXT",
            "education_json": "TEXT NOT NULL DEFAULT '[]'",
            "skills_text": "TEXT",
            "skills_json": "TEXT NOT NULL DEFAULT '[]'",
            "experiences_json": "TEXT NOT NULL DEFAULT '[]'",
            "certificates_json": "TEXT NOT NULL DEFAULT '[]'",
            "contact_data": "TEXT NOT NULL DEFAULT '{}'",
        },
    )
    _ensure_table_columns(
        "projects",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "github_url": "VARCHAR(500)",
            "tech_stack": "TEXT",
            "stars": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    _ensure_table_columns(
        "analytics_events",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        "custom_domains",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        "deployments",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_table_columns(
        "oauth_connections",
        {
            "created_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        },
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_legacy_schema_compatibility()
        except OperationalError as exc:
            raise RuntimeError(
                "Database startup failed. Check DATABASE_URL in .env, verify the PostgreSQL "
                "user/password, and confirm the target database exists before starting Uvicorn."
            ) from exc
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,
)


app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(api_router)
app.include_router(public_router)
