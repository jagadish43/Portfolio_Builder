from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import OperationalError

from app.api.routes import router as api_router
from app.config import get_settings
from app.database import Base, engine
from app.public.views import router as public_router


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        try:
            Base.metadata.create_all(bind=engine)
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
