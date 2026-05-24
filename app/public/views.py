import re
from typing import Any

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload

from app.auth import hash_password, verify_password
from app.config import TEMPLATES_DIR, get_settings
from app.database import get_db
from app.models import Portfolio, Project, User


router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")


def _is_local_request(request: Request) -> bool:
    return request.url.hostname in {"localhost", "127.0.0.1"}


def _extract_subdomain(request: Request) -> str | None:
    settings = get_settings()
    forwarded_host = request.headers.get("x-forwarded-host")
    host_header = forwarded_host or request.headers.get("host", "")
    host = host_header.split(",")[0].strip().split(":")[0].lower()

    if not host:
        return None

    if host in {"localhost", "127.0.0.1"}:
        value = request.query_params.get("subdomain")
        return value.lower().strip() if value else None

    if host == settings.root_domain:
        return None

    if host.endswith(f".{settings.root_domain}"):
        return host[: -(len(settings.root_domain) + 1)] or None

    host_parts = host.split(".")
    if len(host_parts) >= 3:
        return host_parts[0]

    return None


def _extract_skills_from_bio(bio: str) -> list[str]:
    for line in bio.splitlines():
        normalized_line = line.strip()
        if normalized_line.lower().startswith("skills:"):
            _, raw_skills = normalized_line.split(":", maxsplit=1)
            return [skill.strip() for skill in raw_skills.split(",") if skill.strip()]
    return []


def _build_site_url(request: Request, subdomain: str) -> str:
    settings = get_settings()
    if _is_local_request(request):
        return str(request.url.replace(path="/", query=f"subdomain={subdomain}"))
    return f"{settings.default_site_scheme}://{subdomain}.{settings.root_domain}"


def _get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return None
    return db.get(User, user_id)


def _render_template(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    payload = {"current_user": None, **(context or {})}
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=payload,
        status_code=status_code,
    )


def _render_auth_page(
    request: Request,
    mode: str,
    error: str | None = None,
    email: str = "",
) -> HTMLResponse:
    return _render_template(
        request,
        "auth.html",
        {
            "mode": mode,
            "error": error,
            "email": email,
        },
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _render_dashboard(request: Request, user: User, portfolios: list[Portfolio]) -> HTMLResponse:
    items = [
        {
            "id": portfolio.id,
            "subdomain": portfolio.subdomain,
            "full_name": portfolio.full_name,
            "title_tagline": portfolio.title_tagline,
            "is_published": portfolio.is_published,
            "project_count": len(portfolio.projects),
            "preview_url": _build_site_url(request, portfolio.subdomain),
        }
        for portfolio in portfolios
    ]
    return _render_template(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "portfolios": items,
        },
    )


def _render_portfolio_form(
    request: Request,
    user: User,
    error: str | None = None,
    form_data: dict[str, Any] | None = None,
) -> HTMLResponse:
    defaults = {
        "subdomain": "",
        "full_name": "",
        "title_tagline": "",
        "bio": "",
        "theme_slug": "default",
        "is_published": True,
        "project_title": "",
        "project_description": "",
        "project_live_url": "",
    }
    if form_data:
        defaults.update(form_data)
    return _render_template(
        request,
        "portfolio_form.html",
        {
            "current_user": user,
            "error": error,
            "form_data": defaults,
        },
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _render_local_landing(request: Request) -> HTMLResponse:
    return _render_template(request, "landing.html")


def _render_not_found(request: Request) -> HTMLResponse:
    return _render_template(
        request,
        "404.html",
        {"requested_host": request.headers.get("host", "")},
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _load_user_portfolios(db: Session, user_id: int) -> list[Portfolio]:
    return (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.user_id == user_id)
        .order_by(Portfolio.id.asc())
        .all()
    )


def _require_user(request: Request, db: Session) -> User | RedirectResponse:
    user = _get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return user


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def render_public_portfolio(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    subdomain = _extract_subdomain(request)
    if not subdomain:
        if _is_local_request(request):
            user = _get_current_user(request, db)
            if user is None:
                return _render_local_landing(request)
            return _render_dashboard(request, user, _load_user_portfolios(db, user.id))
        return _render_not_found(request)

    portfolio = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.subdomain == subdomain, Portfolio.is_published.is_(True))
        .first()
    )
    if portfolio is None:
        return _render_not_found(request)

    context: dict[str, Any] = {
        "portfolio": portfolio,
        "projects": portfolio.projects,
        "skills": _extract_skills_from_bio(portfolio.bio),
        "site_url": _build_site_url(request, portfolio.subdomain),
    }
    return templates.TemplateResponse(
        request=request,
        name="portfolio.html",
        context=context,
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _get_current_user(request, db)
    if user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return _render_auth_page(request, mode="login")


@router.post("/login", include_in_schema=False)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
 
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    if user is None or not verify_password(password, user.password_hash):
        return _render_auth_page(
            request,
            mode="login",
            error="Invalid email or password.",
            email=normalized_email,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def signup_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _get_current_user(request, db)
    if user is not None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return _render_auth_page(request, mode="signup")


@router.post("/signup", include_in_schema=False)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:

    normalized_email = email.strip().lower()

    if "@" not in normalized_email:
        return _render_auth_page(
            request,
            mode="signup",
            error="Enter a valid email address.",
            email=normalized_email,
        )
    if len(password) < 8:
        return _render_auth_page(
            request,
            mode="signup",
            error="Password must be at least 8 characters.",
            email=normalized_email,
        )
    if password != confirm_password:
        return _render_auth_page(
            request,
            mode="signup",
            error="Passwords do not match.",
            email=normalized_email,
        )
    if db.query(User).filter(User.email == normalized_email).first() is not None:
        return _render_auth_page(
            request,
            mode="signup",
            error="An account already exists for that email.",
            email=normalized_email,
        )

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/portfolios/new", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", include_in_schema=False)
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portfolios/new", response_class=HTMLResponse, include_in_schema=False)
async def new_portfolio_page(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
 
    user = _require_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    return _render_portfolio_form(request, user)


@router.post("/portfolios/new", include_in_schema=False)
async def create_portfolio(
    request: Request,
    subdomain: str = Form(...),
    full_name: str = Form(...),
    title_tagline: str = Form(...),
    bio: str = Form(...),
    theme_slug: str = Form("default"),
    is_published: str | None = Form(None),
    project_title: str = Form(""),
    project_description: str = Form(""),
    project_live_url: str = Form(""),
    db: Session = Depends(get_db),
) -> Response:

    user = _require_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    normalized_subdomain = subdomain.strip().lower()
    normalized_theme = theme_slug.strip().lower() or "default"
    cleaned_data = {
        "subdomain": normalized_subdomain,
        "full_name": full_name.strip(),
        "title_tagline": title_tagline.strip(),
        "bio": bio.strip(),
        "theme_slug": normalized_theme,
        "is_published": is_published is not None,
        "project_title": project_title.strip(),
        "project_description": project_description.strip(),
        "project_live_url": project_live_url.strip(),
    }

    if not all(
        [
            cleaned_data["subdomain"],
            cleaned_data["full_name"],
            cleaned_data["title_tagline"],
            cleaned_data["bio"],
        ]
    ):
        return _render_portfolio_form(
            request,
            user,
            error="Fill in all required portfolio details.",
            form_data=cleaned_data,
        )

    if not SUBDOMAIN_PATTERN.match(normalized_subdomain):
        return _render_portfolio_form(
            request,
            user,
            error="Subdomain must be 3-63 characters using lowercase letters, numbers, or hyphens.",
            form_data=cleaned_data,
        )

    if db.query(Portfolio).filter(Portfolio.subdomain == normalized_subdomain).first() is not None:
        return _render_portfolio_form(
            request,
            user,
            error="That subdomain is already in use.",
            form_data=cleaned_data,
        )

    has_project_title = bool(cleaned_data["project_title"])
    has_project_description = bool(cleaned_data["project_description"])
    if has_project_title != has_project_description:
        return _render_portfolio_form(
            request,
            user,
            error="Provide both first project title and description, or leave both empty.",
            form_data=cleaned_data,
        )

    portfolio = Portfolio(
        user_id=user.id,
        subdomain=normalized_subdomain,
        theme_slug=normalized_theme,
        full_name=cleaned_data["full_name"],
        title_tagline=cleaned_data["title_tagline"],
        bio=cleaned_data["bio"],
        is_published=cleaned_data["is_published"],
    )
    db.add(portfolio)
    db.flush()

    if has_project_title and has_project_description:
        db.add(
            Project(
                portfolio_id=portfolio.id,
                title=cleaned_data["project_title"],
                description=cleaned_data["project_description"],
                live_url=cleaned_data["project_live_url"] or None,
                display_order=0,
            )
        )

    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
