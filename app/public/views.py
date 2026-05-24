import json
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

SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
CONTACT_FIELDS = ("github", "leetcode", "linkedin", "email", "phone")
PRIMARY_THEME_SLUG = "default_template1"
PRIMARY_THEME_TEMPLATE = "Templates/Default_Template1.html"
BACKGROUND_THEME_OPTIONS = ("ivory", "mint", "sky", "peach", "slate")
THEME_OPTIONS = (
    {
        "slug": PRIMARY_THEME_SLUG,
        "label": "Template 1",
        "description": "Left sidebar portfolio with scrolling content and editorial sections.",
    },
)
THEME_TEMPLATE_MAP = {
    PRIMARY_THEME_SLUG: PRIMARY_THEME_TEMPLATE,
}


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


def _parse_json_object(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not raw:
        return dict(fallback or {})
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return dict(fallback or {})
    return value if isinstance(value, dict) else dict(fallback or {})


def _parse_json_list(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _parse_skills(raw: str | None, bio: str = "") -> list[str]:
    source = (raw or "").strip()
    if source:
        tokens = re.split(r"[\n,]", source)
        return [token.strip() for token in tokens if token.strip()]
    return _extract_skills_from_bio(bio)


def _normalize_section_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = raw or {}
    contact_fields = payload.get("contact_fields", {})
    background_theme = str(payload.get("background_theme", "ivory")).strip().lower()
    return {
        "education": True,
        "projects": True,
        "experience": bool(payload.get("experience", False)),
        "skills": True,
        "certificates": True,
        "contact": bool(payload.get("contact", False)),
        "background_theme": (
            background_theme if background_theme in BACKGROUND_THEME_OPTIONS else "ivory"
        ),
        "contact_fields": {
            name: bool(contact_fields.get(name, False)) for name in CONTACT_FIELDS
        },
    }


def _default_form_data() -> dict[str, Any]:
    return {
        "step": "customize",
        "subdomain": "",
        "full_name": "",
        "title_tagline": "",
        "bio": "",
        "theme_slug": PRIMARY_THEME_SLUG,
        "is_published": True,
        "education_text": "",
        "skills_text": "",
        "github_url": "",
        "leetcode_url": "",
        "linkedin_url": "",
        "contact_email": "",
        "phone_number": "",
        "resume_url": "",
        "sections": _normalize_section_config(),
        "projects": [{"title": "", "description": "", "live_url": ""}],
        "experiences": [{"role": "", "company": "", "duration": "", "description": ""}],
        "certificates": [{"name": "", "issuer": "", "year": "", "url": ""}],
    }


def _theme_slugs() -> set[str]:
    return {theme["slug"] for theme in THEME_OPTIONS}


def _normalize_theme_slug(theme_slug: str | None) -> str:
    normalized = (theme_slug or "").strip().lower()
    return normalized if normalized in _theme_slugs() else PRIMARY_THEME_SLUG


def _resolve_portfolio_template(theme_slug: str | None) -> str:
    return THEME_TEMPLATE_MAP.get(_normalize_theme_slug(theme_slug), PRIMARY_THEME_TEMPLATE)


def _sections_from_form(form: Any) -> dict[str, Any]:
    return _normalize_section_config(
        {
            "experience": form.get("section_experience") == "yes",
            "contact": form.get("section_contact") == "yes",
            "background_theme": form.get("background_theme", "ivory"),
            "contact_fields": {
                "github": "contact_field_github" in form,
                "leetcode": "contact_field_leetcode" in form,
                "linkedin": "contact_field_linkedin" in form,
                "email": "contact_field_email" in form,
                "phone": "contact_field_phone" in form,
            },
        }
    )


def _deserialize_portfolio(portfolio: Portfolio) -> dict[str, Any]:
    contact_data = _parse_json_object(portfolio.contact_data)
    sections = _normalize_section_config(_parse_json_object(portfolio.section_config))
    return {
        "sections": sections,
        "education_text": portfolio.education_text or "",
        "skills": _parse_skills(portfolio.skills_text, portfolio.bio),
        "experiences": _parse_json_list(portfolio.experiences_json),
        "certificates": _parse_json_list(portfolio.certificates_json),
        "contact_data": contact_data,
        "contact_items": [
            ("GitHub", contact_data.get("github_url", "")),
            ("LeetCode", contact_data.get("leetcode_url", "")),
            ("LinkedIn", contact_data.get("linkedin_url", "")),
            ("Email", contact_data.get("contact_email", "")),
            ("Phone Number", contact_data.get("phone_number", "")),
        ],
        "resume_url": contact_data.get("resume_url", ""),
        "contact_visibility": {
            "contact": bool(contact_data.get("display_contact", sections["contact"])),
            "github": bool(contact_data.get("display_github", sections["contact_fields"]["github"])),
            "leetcode": bool(
                contact_data.get("display_leetcode", sections["contact_fields"]["leetcode"])
            ),
            "linkedin": bool(
                contact_data.get("display_linkedin", sections["contact_fields"]["linkedin"])
            ),
            "email": bool(contact_data.get("display_email", sections["contact_fields"]["email"])),
            "phone": bool(contact_data.get("display_phone", sections["contact_fields"]["phone"])),
            "resume": bool(contact_data.get("display_resume", bool(contact_data.get("resume_url")))),
        },
    }


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
            "theme_slug": portfolio.theme_slug,
            "is_published": portfolio.is_published,
            "project_count": len(portfolio.projects),
            "preview_url": _build_site_url(request, portfolio.subdomain),
            "edit_url": f"/portfolios/{portfolio.id}/edit",
        }
        for portfolio in portfolios
    ]
    return _render_template(
        request,
        "dashboard.html",
        {
            "current_user": user,
            "portfolios": items,
            "can_create_portfolio": not portfolios,
        },
    )


def _render_portfolio_form(
    request: Request,
    user: User,
    error: str | None = None,
    form_data: dict[str, Any] | None = None,
    step: str | None = None,
    form_action: str = "/portfolios/new",
    form_mode: str = "create",
) -> HTMLResponse:
    defaults = _default_form_data()

    if form_mode == "create":
        defaults["contact_email"] = user.email

    if form_data:
        defaults.update(form_data)
    defaults["step"] = step or defaults.get("step", "customize")
    return _render_template(
        request,
        "portfolio_form.html",
        {
            "current_user": user,
            "error": error,
            "form_data": defaults,
            "theme_options": THEME_OPTIONS,
            "form_action": form_action,
            "form_mode": form_mode,
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


def _get_primary_portfolio(db: Session, user_id: int) -> Portfolio | None:
    return (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.user_id == user_id)
        .order_by(Portfolio.id.asc())
        .first()
    )


def _require_user(request: Request, db: Session) -> User | RedirectResponse:
    user = _get_current_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return user


def _portfolio_to_form_data(portfolio: Portfolio) -> dict[str, Any]:
    details = _deserialize_portfolio(portfolio)
    contact_data = details["contact_data"]
    return {
        "step": "details",
        "subdomain": portfolio.subdomain,
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
        "theme_slug": _normalize_theme_slug(portfolio.theme_slug),
        "is_published": portfolio.is_published,
        "education_text": portfolio.education_text or "",
        "skills_text": portfolio.skills_text or "",
        "github_url": contact_data.get("github_url", ""),
        "leetcode_url": contact_data.get("leetcode_url", ""),
        "linkedin_url": contact_data.get("linkedin_url", ""),
        "contact_email": contact_data.get("contact_email", ""),
        "phone_number": contact_data.get("phone_number", ""),
        "resume_url": contact_data.get("resume_url", ""),
        "sections": details["sections"],
        "projects": [
            {
                "title": project.title,
                "description": project.description,
                "live_url": project.live_url or "",
            }
            for project in portfolio.projects
        ]
        or _default_form_data()["projects"],
        "experiences": details["experiences"] or _default_form_data()["experiences"],
        "certificates": details["certificates"] or _default_form_data()["certificates"],
    }


def _collect_portfolio_form_data(form: Any) -> dict[str, Any]:
    def cleaned_list(name: str) -> list[str]:
        return [value.strip() for value in form.getlist(name)]

    sections = _sections_from_form(form)
    normalized_subdomain = form.get("subdomain", "").strip().lower()
    normalized_theme = _normalize_theme_slug(form.get("theme_slug"))
    cleaned_data = {
        "subdomain": normalized_subdomain,
        "full_name": form.get("full_name", "").strip(),
        "title_tagline": form.get("title_tagline", "").strip(),
        "bio": form.get("bio", "").strip(),
        "theme_slug": normalized_theme,
        "is_published": form.get("is_published") is not None,
        "education_text": form.get("education_text", "").strip(),
        "skills_text": form.get("skills_text", "").strip(),
        "github_url": form.get("github_url", "").strip(),
        "leetcode_url": form.get("leetcode_url", "").strip(),
        "linkedin_url": form.get("linkedin_url", "").strip(),
        "contact_email": form.get("contact_email", "").strip(),
        "phone_number": form.get("phone_number", "").strip(),
        "resume_url": form.get("resume_url", "").strip(),
        "sections": sections,
        "step": "details",
    }

    project_titles = cleaned_list("project_title")
    project_descriptions = cleaned_list("project_description")
    project_urls = cleaned_list("project_live_url")
    max_project_items = max(len(project_titles), len(project_descriptions), len(project_urls), 1)
    projects: list[dict[str, str]] = []
    for index in range(max_project_items):
        item = {
            "title": project_titles[index] if index < len(project_titles) else "",
            "description": project_descriptions[index] if index < len(project_descriptions) else "",
            "live_url": project_urls[index] if index < len(project_urls) else "",
        }
        if any(item.values()):
            projects.append(item)

    experience_roles = cleaned_list("experience_role")
    experience_companies = cleaned_list("experience_company")
    experience_durations = cleaned_list("experience_duration")
    experience_descriptions = cleaned_list("experience_description")
    max_experience_items = max(
        len(experience_roles),
        len(experience_companies),
        len(experience_durations),
        len(experience_descriptions),
        1,
    )
    experiences: list[dict[str, str]] = []
    for index in range(max_experience_items):
        item = {
            "role": experience_roles[index] if index < len(experience_roles) else "",
            "company": experience_companies[index] if index < len(experience_companies) else "",
            "duration": experience_durations[index] if index < len(experience_durations) else "",
            "description": experience_descriptions[index] if index < len(experience_descriptions) else "",
        }
        if any(item.values()):
            experiences.append(item)

    certificate_names = cleaned_list("certificate_name")
    certificate_issuers = cleaned_list("certificate_issuer")
    certificate_years = cleaned_list("certificate_year")
    certificate_urls = cleaned_list("certificate_url")
    max_certificate_items = max(
        len(certificate_names),
        len(certificate_issuers),
        len(certificate_years),
        len(certificate_urls),
        1,
    )
    certificates: list[dict[str, str]] = []
    for index in range(max_certificate_items):
        item = {
            "name": certificate_names[index] if index < len(certificate_names) else "",
            "issuer": certificate_issuers[index] if index < len(certificate_issuers) else "",
            "year": certificate_years[index] if index < len(certificate_years) else "",
            "url": certificate_urls[index] if index < len(certificate_urls) else "",
        }
        if any(item.values()):
            certificates.append(item)

    cleaned_data["projects"] = projects or _default_form_data()["projects"]
    cleaned_data["experiences"] = experiences or _default_form_data()["experiences"]
    cleaned_data["certificates"] = certificates or _default_form_data()["certificates"]
    return cleaned_data


def _validate_portfolio_form_data(
    cleaned_data: dict[str, Any],
    db: Session,
    existing_portfolio: Portfolio | None = None,
) -> str | None:
    normalized_subdomain = cleaned_data["subdomain"]
    normalized_theme = cleaned_data["theme_slug"]
    sections = cleaned_data["sections"]
    projects = cleaned_data["projects"]
    experiences = cleaned_data["experiences"]
    certificates = cleaned_data["certificates"]

    if not all(
        [
            cleaned_data["subdomain"],
            cleaned_data["full_name"],
            cleaned_data["title_tagline"],
        ]
    ):
        return "Fill in all required portfolio details."

    if not cleaned_data["education_text"]:
        return "Education is mandatory."

    if not _parse_skills(cleaned_data["skills_text"]):
        return "Add at least one skill."

    if not SUBDOMAIN_PATTERN.match(normalized_subdomain):
        return "Subdomain must be 3-63 characters using lowercase letters, numbers, or hyphens."

    if normalized_theme not in _theme_slugs():
        return "Choose a valid theme option."

    subdomain_query = db.query(Portfolio).filter(Portfolio.subdomain == normalized_subdomain)
    if existing_portfolio is not None:
        subdomain_query = subdomain_query.filter(Portfolio.id != existing_portfolio.id)
    if subdomain_query.first() is not None:
        return "That subdomain is already in use."

    invalid_project = any(bool(item["title"]) != bool(item["description"]) for item in projects)
    if invalid_project:
        return "Each project needs both a title and description."

    valid_projects = [item for item in projects if item["title"] and item["description"]]
    if not valid_projects:
        return "Add at least one project."

    invalid_experience = any(
        any(item.values()) and (not item["role"] or not item["company"] or not item["description"])
        for item in experiences
    )
    if invalid_experience:
        return "Each experience entry must include role, company, and description."

    invalid_certificate = any(
        any(item.values()) and (not item["name"] or not item["issuer"])
        for item in certificates
    )
    if invalid_certificate:
        return "Each certificate entry must include a certificate name and issuer."

    valid_certificates = [item for item in certificates if item["name"] and item["issuer"]]
    if not valid_certificates:
        return "Add at least one certificate."

    if sections["contact"] and not any(sections["contact_fields"].values()):
        return "Select at least one contact field when Contact Information is enabled."

    contact_key_map = {
        "github": "github_url",
        "leetcode": "leetcode_url",
        "linkedin": "linkedin_url",
        "email": "contact_email",
        "phone": "phone_number",
    }
    if sections["contact"]:
        missing_contact_values = [
            field
            for field, enabled in sections["contact_fields"].items()
            if enabled and not cleaned_data[contact_key_map[field]]
        ]
        if missing_contact_values:
            return "Fill in each enabled contact field."

    cleaned_data["valid_projects"] = valid_projects
    cleaned_data["valid_experiences"] = [
        item for item in experiences if item["role"] and item["company"] and item["description"]
    ]
    cleaned_data["valid_certificates"] = valid_certificates
    cleaned_data["contact_data"] = {
        "display_contact": bool(sections["contact"]),
        "display_github": bool(sections["contact_fields"]["github"]),
        "display_leetcode": bool(sections["contact_fields"]["leetcode"]),
        "display_linkedin": bool(sections["contact_fields"]["linkedin"]),
        "display_email": bool(sections["contact_fields"]["email"]),
        "display_phone": bool(sections["contact_fields"]["phone"]),
        "display_resume": bool(sections["contact"] and cleaned_data["resume_url"]),
        "github_url": cleaned_data["github_url"] if sections["contact_fields"]["github"] else "",
        "leetcode_url": cleaned_data["leetcode_url"] if sections["contact_fields"]["leetcode"] else "",
        "linkedin_url": cleaned_data["linkedin_url"] if sections["contact_fields"]["linkedin"] else "",
        "contact_email": cleaned_data["contact_email"] if sections["contact_fields"]["email"] else "",
        "phone_number": cleaned_data["phone_number"] if sections["contact_fields"]["phone"] else "",
        "resume_url": cleaned_data["resume_url"] if sections["contact"] else "",
    }
    return None


def _save_portfolio(
    db: Session,
    user: User,
    cleaned_data: dict[str, Any],
    portfolio: Portfolio | None = None,
) -> Portfolio:
    target = portfolio or Portfolio(user_id=user.id, subdomain=cleaned_data["subdomain"])
    target.subdomain = cleaned_data["subdomain"]
    target.theme_slug = cleaned_data["theme_slug"]
    target.full_name = cleaned_data["full_name"]
    target.title_tagline = cleaned_data["title_tagline"]
    target.bio = cleaned_data["bio"]
    target.section_config = json.dumps(cleaned_data["sections"])
    target.education_text = cleaned_data["education_text"]
    target.skills_text = cleaned_data["skills_text"]
    target.experiences_json = json.dumps(
        cleaned_data["valid_experiences"] if cleaned_data["sections"]["experience"] else []
    )
    target.certificates_json = json.dumps(cleaned_data["valid_certificates"])
    target.contact_data = json.dumps(cleaned_data["contact_data"])
    target.is_published = cleaned_data["is_published"]
    target.projects = [
        Project(
            title=item["title"],
            description=item["description"],
            live_url=item["live_url"] or None,
            display_order=index,
        )
        for index, item in enumerate(cleaned_data["valid_projects"])
    ]

    if portfolio is None:
        db.add(target)

    db.commit()
    db.refresh(target)
    return target


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def render_public_portfolio(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    subdomain = _extract_subdomain(request)
    if not subdomain:
        user = _get_current_user(request, db)
        if user is None:
            return _render_local_landing(request)
        return _render_dashboard(request, user, _load_user_portfolios(db, user.id))

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
        "site_url": _build_site_url(request, portfolio.subdomain),
        **_deserialize_portfolio(portfolio),
    }
    return templates.TemplateResponse(
        request=request,
        name=_resolve_portfolio_template(portfolio.theme_slug),
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
    return RedirectResponse(url="/portfolios/new", status_code=status.HTTP_303_SEE_OTHER)


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
    if password != confirm_password:
        return _render_auth_page(
            request,
            mode="signup",
            error="Passwords do not match.",
            email=normalized_email,
        )

    if db.query(User).filter(User.email == normalized_email).first():
        return _render_auth_page(
            request,
            mode="signup",
            error="That email is already registered.",
            email=normalized_email,
        )

    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/portfolios/new", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout", include_in_schema=False)
async def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout", include_in_schema=False)
async def logout_post(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/portfolios/new", response_class=HTMLResponse, include_in_schema=False)
async def new_portfolio_page(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user

    existing_portfolio = _get_primary_portfolio(db, user.id)
    if existing_portfolio:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return _render_portfolio_form(request, user)


@router.post("/portfolios/new", include_in_schema=False)
async def create_portfolio(request: Request, db: Session = Depends(get_db)) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user

    form_data = await request.form()
    nav = form_data.get("nav")
    step = form_data.get("step", "customize")
    cleaned_data = _collect_portfolio_form_data(form_data)

    if nav == "customize":
        return _render_portfolio_form(
            request,
            user,
            form_data=cleaned_data,
            step="customize",
        )

    if step == "customize":
        return _render_portfolio_form(
            request,
            user,
            form_data=cleaned_data,
            step="details",
        )

    error = _validate_portfolio_form_data(cleaned_data, db)

    if error:
        return _render_portfolio_form(
            request,
            user,
            error=error,
            form_data=cleaned_data,
            step="details",
        )

    _save_portfolio(db, user, cleaned_data)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/portfolios/{portfolio_id}/edit", response_class=HTMLResponse, include_in_schema=False
)
async def edit_portfolio_page(
    portfolio_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user

    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user.id:
        return _render_not_found(request)

    return _render_portfolio_form(
        request,
        user,
        form_data=_portfolio_to_form_data(portfolio),
        form_action=f"/portfolios/{portfolio.id}/edit",
        form_mode="edit",
    )


@router.post("/portfolios/{portfolio_id}/edit", include_in_schema=False)
async def update_portfolio(
    portfolio_id: int, request: Request, db: Session = Depends(get_db)
) -> Response:
    user = _require_user(request, db)
    if isinstance(user, Response):
        return user

    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user.id:
        return _render_not_found(request)

    form_data = await request.form()
    nav = form_data.get("nav")
    step = form_data.get("step", "customize")
    cleaned_data = _collect_portfolio_form_data(form_data)

    if nav == "customize":
        return _render_portfolio_form(
            request,
            user,
            form_data=cleaned_data,
            step="customize",
            form_action=f"/portfolios/{portfolio.id}/edit",
            form_mode="edit",
        )

    if step == "customize":
        return _render_portfolio_form(
            request,
            user,
            form_data=cleaned_data,
            step="details",
            form_action=f"/portfolios/{portfolio.id}/edit",
            form_mode="edit",
        )

    error = _validate_portfolio_form_data(cleaned_data, db, existing_portfolio=portfolio)

    if error:
        return _render_portfolio_form(
            request,
            user,
            error=error,
            form_data=cleaned_data,
            step="details",
            form_action=f"/portfolios/{portfolio.id}/edit",
            form_mode="edit",
        )

    _save_portfolio(db, user, cleaned_data, portfolio=portfolio)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
