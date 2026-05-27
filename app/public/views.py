from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, selectinload

from app.auth import hash_password, verify_password
from app.config import TEMPLATES_DIR, get_settings
from app.database import get_db
from app.models import Portfolio, User
from app.services.analytics_service import build_summary
from app.services.csrf_service import get_or_create_csrf_token, validate_csrf_request
from app.services.portfolio_service import (
    default_form_state,
    deserialize_portfolio,
    load_portfolio_for_user,
    load_primary_portfolio,
    load_user_portfolios,
    normalize_education_entries,
    normalize_skill_categories,
    persist_portfolio,
    serialize_portfolio,
    validate_portfolio_payload,
)
from app.services.template_service import get_template_options, resolve_template
from app.utils.json_tools import parse_json_list
from app.utils.portfolio_defaults import (
    CONTACT_FIELDS,
    DEFAULT_EDUCATION_TYPES,
    DEFAULT_SKILL_CATEGORIES,
    normalize_section_config,
    normalize_section_order,
)


router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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


def _flash_message(request: Request, level: str, message: str) -> None:
    existing = request.session.get("toast_messages", [])
    messages = existing if isinstance(existing, list) else []
    messages.append({"level": level, "message": message})
    request.session["toast_messages"] = messages


def _consume_flash_messages(request: Request) -> list[dict[str, str]]:
    raw_messages = request.session.pop("toast_messages", [])
    return raw_messages if isinstance(raw_messages, list) else []


def _render_template(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    payload = dict(context or {})
    page_toasts = payload.pop("toast_messages", [])
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={
            "current_user": payload.pop("current_user", None),
            "csrf_token": get_or_create_csrf_token(request),
            "toast_messages": [*_consume_flash_messages(request), *page_toasts],
            **payload,
        },
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
            "email": email,
            "toast_messages": [{"level": "error", "message": error}] if error else [],
        },
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _render_dashboard(request: Request, user: User, portfolios: list[Portfolio], db: Session) -> HTMLResponse:
    items = []
    for portfolio in portfolios:
        summary = build_summary(db, portfolio.id, 7)
        items.append(
            {
                "id": portfolio.id,
                "subdomain": portfolio.subdomain,
                "full_name": portfolio.full_name,
                "title_tagline": portfolio.title_tagline,
                "theme_slug": portfolio.theme_slug,
                "is_published": portfolio.is_published,
                "project_count": len(portfolio.projects),
                "preview_url": _build_site_url(request, portfolio.subdomain),
                "edit_url": f"/portfolios/{portfolio.id}/edit",
                "resume_export_url": f"/api/portfolios/{portfolio.id}/resume.pdf",
                "analytics": summary,
                "domains": [domain.domain for domain in portfolio.custom_domains],
                "latest_deployment": portfolio.deployments[0] if portfolio.deployments else None,
            }
        )
    return _render_template(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "portfolios": items,
            "can_create_portfolio": not portfolios,
        },
    )


def _render_form(
    request: Request,
    user: User,
    form_data: dict[str, Any] | None = None,
    error: str | None = None,
    form_action: str = "/portfolios/new",
    form_mode: str = "create",
) -> HTMLResponse:
    payload = default_form_state(user.email)
    if form_data:
        payload.update(form_data)
    return _render_template(
        request,
        "portfolio_form.html",
        {
            "current_user": user,
            "form_data": payload,
            "theme_options": get_template_options(),
            "font_options": ["Space Grotesk", "IBM Plex Sans", "DM Sans", "Manrope"],
            "education_type_options": list(DEFAULT_EDUCATION_TYPES),
            "skill_category_options": list(DEFAULT_SKILL_CATEGORIES),
            "form_action": form_action,
            "form_mode": form_mode,
            "toast_messages": [{"level": "warning", "message": error}] if error else [],
        },
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


def _require_user(request: Request, db: Session) -> User | RedirectResponse:
    user = _get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return user


def _parse_named_rows(form: Any, fields: tuple[str, ...], prefix: str) -> list[dict[str, str]]:
    values = {field: [item.strip() for item in form.getlist(f"{prefix}_{field}")] for field in fields}
    count = max([len(items) for items in values.values()] + [1])
    rows: list[dict[str, str]] = []
    for index in range(count):
        row = {field: values[field][index] if index < len(values[field]) else "" for field in fields}
        if any(row.values()):
            rows.append(row)
    return rows


def _collect_form_payload(form: Any) -> dict[str, Any]:
    section_order = normalize_section_order(form.getlist("section_order"))
    sections = normalize_section_config(
        {
            "experience": form.get("section_experience") == "yes",
            "contact": form.get("section_contact") == "yes",
            "contact_fields": {
                "github": "contact_field_github" in form,
                "leetcode": "contact_field_leetcode" in form,
                "linkedin": "contact_field_linkedin" in form,
                "email": "contact_field_email" in form,
                "phone": "contact_field_phone" in form,
            },
        }
    )
    contact_data = {
        "display_contact": bool(sections["contact"]),
        "display_github": bool(sections["contact_fields"]["github"]),
        "display_leetcode": bool(sections["contact_fields"]["leetcode"]),
        "display_linkedin": bool(sections["contact_fields"]["linkedin"]),
        "display_email": bool(sections["contact_fields"]["email"]),
        "display_phone": bool(sections["contact_fields"]["phone"]),
        "display_resume": bool(form.get("resume_url")),
        "github_url": form.get("github_url", "").strip(),
        "leetcode_url": form.get("leetcode_url", "").strip(),
        "linkedin_url": form.get("linkedin_url", "").strip(),
        "contact_email": form.get("contact_email", "").strip(),
        "phone_number": form.get("phone_number", "").strip(),
        "resume_url": form.get("resume_url", "").strip(),
    }
    theme_config = {
        "primary_color": form.get("primary_color", "#0f766e"),
        "accent_color": form.get("accent_color", "#f97316"),
        "background_color": form.get("background_color", "#f8fafc"),
        "surface_color": form.get("surface_color", "#ffffff"),
        "text_color": form.get("text_color", "#0f172a"),
        "font_family": form.get("font_family", "Space Grotesk"),
        "mode": form.get("mode", "light"),
    }
    education_entries = normalize_education_entries(
        parse_json_list(form.get("education_json") or "[]"),
        form.get("education_text", "").strip(),
    )
    skill_categories = normalize_skill_categories(
        parse_json_list(form.get("skills_json") or "[]"),
        form.get("skills_text", "").strip(),
    )
    return {
        "subdomain": form.get("subdomain", "").strip().lower(),
        "theme_slug": form.get("theme_slug", "modern"),
        "full_name": form.get("full_name", "").strip(),
        "title_tagline": form.get("title_tagline", "").strip(),
        "bio": form.get("bio", "").strip(),
        "section_config": sections,
        "section_order": section_order,
        "theme_config": theme_config,
        "education_text": form.get("education_text", "").strip(),
        "education_entries": education_entries,
        "skills_text": form.get("skills_text", "").strip(),
        "skill_categories": skill_categories,
        "experiences": _parse_named_rows(form, ("role", "company", "duration", "description"), "experience"),
        "certificates": _parse_named_rows(form, ("name", "issuer", "year", "url"), "certificate"),
        "contact_data": contact_data,
        "is_published": form.get("is_published") == "on",
        "projects": _parse_named_rows(form, ("title", "description", "live_url", "github_url", "tech_stack"), "project"),
    }


def _portfolio_to_form_data(portfolio: Portfolio) -> dict[str, Any]:
    details = deserialize_portfolio(portfolio)
    contact = details["contact_data"]
    return {
        "subdomain": portfolio.subdomain,
        "theme_slug": portfolio.theme_slug,
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
        "section_order": details["section_order"],
        "theme_config": details["theme_config"],
        "education_text": portfolio.education_text or "",
        "education_entries": details["education_entries"] or default_form_state()["education_entries"],
        "skills_text": portfolio.skills_text or "",
        "skill_categories": details["skill_categories"] or default_form_state()["skill_categories"],
        "experiences": details["experiences"] or default_form_state()["experiences"],
        "certificates": details["certificates"] or default_form_state()["certificates"],
        "projects": [
            {
                "title": item.title,
                "description": item.description,
                "live_url": item.live_url or "",
                "github_url": item.github_url or "",
                "tech_stack": item.tech_stack or "",
            }
            for item in portfolio.projects
        ]
        or default_form_state()["projects"],
        "sections": details["section_config"],
        "github_url": contact.get("github_url", ""),
        "leetcode_url": contact.get("leetcode_url", ""),
        "linkedin_url": contact.get("linkedin_url", ""),
        "contact_email": contact.get("contact_email", ""),
        "phone_number": contact.get("phone_number", ""),
        "resume_url": contact.get("resume_url", ""),
        "is_published": portfolio.is_published,
    }


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def render_public_portfolio(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    subdomain = _extract_subdomain(request)
    if not subdomain:
        user = _get_current_user(request, db)
        if user is None:
            return _render_template(request, "landing.html")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    portfolio = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.subdomain == subdomain, Portfolio.is_published.is_(True))
        .first()
    )
    if portfolio is None:
        return _render_template(
            request,
            "404.html",
            {"requested_host": request.headers.get("host", "")},
            status.HTTP_404_NOT_FOUND,
        )

    context = {
        "portfolio": portfolio,
        "projects": portfolio.projects,
        "site_url": _build_site_url(request, portfolio.subdomain),
        **deserialize_portfolio(portfolio),
    }
    return templates.TemplateResponse(
        request=request,
        name=resolve_template(portfolio.theme_slug),
        context=context,
    )


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    return _render_dashboard(request, user, load_user_portfolios(db, user.id), db)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, db: Session = Depends(get_db)) -> Response:
    if _get_current_user(request, db) is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _render_auth_page(request, "login")


@router.post("/login", include_in_schema=False)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    validate_csrf_request(request, csrf_token)
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if user is None or not verify_password(password, user.password_hash):
        return _render_auth_page(request, "login", "Invalid email or password.", normalized_email)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
async def signup_page(request: Request, db: Session = Depends(get_db)) -> Response:
    if _get_current_user(request, db) is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _render_auth_page(request, "signup")


@router.post("/signup", include_in_schema=False)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    validate_csrf_request(request, csrf_token)
    normalized_email = email.strip().lower()
    if password != confirm_password:
        return _render_auth_page(request, "signup", "Passwords do not match.", normalized_email)
    if db.query(User).filter(User.email == normalized_email).first():
        return _render_auth_page(request, "signup", "That email is already registered.", normalized_email)
    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", include_in_schema=False)
async def logout(request: Request, csrf_token: str = Form(...)) -> Response:
    validate_csrf_request(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portfolios/new", response_class=HTMLResponse, include_in_schema=False)
async def new_portfolio_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    if load_primary_portfolio(db, user.id):
        _flash_message(request, "warning", "You already have a portfolio. Edit the existing one instead.")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _render_form(request, user)


@router.post("/portfolios/new", include_in_schema=False)
async def create_portfolio(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    form = await request.form()
    validate_csrf_request(request, form.get("csrf_token"))
    form_payload = _collect_form_payload(form)
    try:
        validated = validate_portfolio_payload(db, user, form_payload)
        persist_portfolio(db, validated)
    except Exception as exc:
        return _render_form(request, user, form_payload, str(getattr(exc, "detail", exc)))
    _flash_message(request, "success", "Portfolio created successfully.")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portfolios/{portfolio_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_portfolio_page(portfolio_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    portfolio = load_portfolio_for_user(db, user.id, portfolio_id)
    if portfolio is None:
        return _render_template(request, "404.html", {"requested_host": request.headers.get("host", "")}, status.HTTP_404_NOT_FOUND)
    return _render_form(
        request,
        user,
        _portfolio_to_form_data(portfolio),
        form_action=f"/portfolios/{portfolio_id}/edit",
        form_mode="edit",
    )


@router.post("/portfolios/{portfolio_id}/edit", include_in_schema=False)
async def update_portfolio_page(portfolio_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    portfolio = load_portfolio_for_user(db, user.id, portfolio_id)
    if portfolio is None:
        return _render_template(request, "404.html", {"requested_host": request.headers.get("host", "")}, status.HTTP_404_NOT_FOUND)
    form = await request.form()
    validate_csrf_request(request, form.get("csrf_token"))
    form_payload = _collect_form_payload(form)
    try:
        validated = validate_portfolio_payload(db, user, form_payload, portfolio=portfolio)
        persist_portfolio(db, validated, portfolio=portfolio)
    except Exception as exc:
        return _render_form(
            request,
            user,
            form_payload,
            str(getattr(exc, "detail", exc)),
            form_action=f"/portfolios/{portfolio_id}/edit",
            form_mode="edit",
        )
    _flash_message(request, "success", "Portfolio updated successfully.")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portfolios/{portfolio_id}/analytics", response_class=HTMLResponse, include_in_schema=False)
async def analytics_page(portfolio_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user
    portfolio = load_portfolio_for_user(db, user.id, portfolio_id)
    if portfolio is None:
        return _render_template(request, "404.html", {"requested_host": request.headers.get("host", "")}, status.HTTP_404_NOT_FOUND)
    return _render_template(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "portfolios": [
                {
                    **serialize_portfolio(portfolio, db),
                    "preview_url": _build_site_url(request, portfolio.subdomain),
                    "edit_url": f"/portfolios/{portfolio.id}/edit",
                    "resume_export_url": f"/api/portfolios/{portfolio.id}/resume.pdf",
                    "analytics": build_summary(db, portfolio.id, 30),
                    "domains": [domain.domain for domain in portfolio.custom_domains],
                    "latest_deployment": portfolio.deployments[0] if portfolio.deployments else None,
                }
            ],
            "can_create_portfolio": False,
        },
    )
