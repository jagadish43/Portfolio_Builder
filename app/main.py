from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.api.routes import router as api_router
from app.config import get_settings
from app.database import Base, engine
from app.public.views import router as public_router


settings = get_settings()


def _ensure_portfolio_columns() -> None:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("portfolios")}
    required_columns = {
        "section_config": "TEXT NOT NULL DEFAULT '{}'",
        "education_text": "TEXT",
        "skills_text": "TEXT",
        "experiences_json": "TEXT NOT NULL DEFAULT '[]'",
        "certificates_json": "TEXT NOT NULL DEFAULT '[]'",
        "contact_data": "TEXT NOT NULL DEFAULT '{}'",
    }
    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            if column_name in existing_columns:
                continue
            connection.exec_driver_sql(
                f"ALTER TABLE portfolios ADD COLUMN {column_name} {column_type}"
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_portfolio_columns()
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
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.include_router(api_router)
app.include_router(public_router)
