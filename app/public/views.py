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

SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
CONTACT_FIELDS = ("github", "leetcode", "linkedin", "email", "phone")
THEME_OPTIONS = (
    {
        "slug": "default",
        "label": "Default Theme",
        "description": "Current split portfolio page with hero, side cards, and section blocks.",
    },
    {
        "slug": "default_template1",
        "label": "Template 1",
        "description": "Left sidebar portfolio with scrolling content and editorial sections.",
    },
    {
        "slug": "default_template2",
        "label": "Template 2",
        "description": "Dark bento dashboard portfolio with cards, stats, and project tiles.",
    },
)


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
    return {
        "education": True,
        "projects": True,
        "experience": bool(payload.get("experience", False)),
        "skills": True,
        "certificates": True,
        "contact": bool(payload.get("contact", False)),
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
        "theme_slug": "default",
        "is_published": True,
        "education_text": "",
        "skills_text": "",
        "github_url": "",
        "leetcode_url": "",
        "linkedin_url": "",
        "contact_email": "",
        "phone_number": "",
        "sections": _normalize_section_config(),
        "projects": [{"title": "", "description": "", "live_url": ""}],
        "experiences": [{"role": "", "company": "", "duration": "", "description": ""}],
        "certificates": [{"name": "", "issuer": "", "year": "", "url": ""}],
    }


def _theme_slugs() -> set[str]:
    return {theme["slug"] for theme in THEME_OPTIONS}


def _sections_from_form(form: Any) -> dict[str, Any]:
    return _normalize_section_config(
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


def _deserialize_portfolio(portfolio: Portfolio) -> dict[str, Any]:
    contact_data = _parse_json_object(portfolio.contact_data)
    return {
        "sections": _normalize_section_config(_parse_json_object(portfolio.section_config)),
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
    step: str = "customize",
) -> HTMLResponse:
    defaults = _default_form_data()
    if form_data:
        defaults.update(form_data)
    defaults["step"] = step
    return _render_template(
        request,
        "portfolio_form.html",
        {
            "current_user": user,
            "error": error,
            "form_data": defaults,
            "theme_options": THEME_OPTIONS,
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
        "site_url": _build_site_url(request, portfolio.subdomain),
        **_deserialize_portfolio(portfolio),
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
    return _render_portfolio_form(request, user, step="customize")


@router.post("/portfolios/new", include_in_schema=False)
async def create_portfolio(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:

    user = _require_user(request, db)
    if isinstance(user, RedirectResponse):
        return user

    form = await request.form()
    step_values = form.getlist("step")
    step = step_values[-1] if step_values else "customize"

    if step == "customize":
        sections = _sections_from_form(form)
        normalized_theme = form.get("theme_slug", "").strip().lower() or "default"
        customize_data = {
            "step": "details",
            "theme_slug": normalized_theme,
            "sections": sections,
        }

        if normalized_theme not in _theme_slugs():
            return _render_portfolio_form(
                request,
                user,
                error="Choose a valid theme option.",
                form_data=customize_data,
                step="customize",
            )

        return _render_portfolio_form(
            request,
            user,
            form_data=customize_data,
            step="details",
        )

    def cleaned_list(name: str) -> list[str]:
        return [value.strip() for value in form.getlist(name)]

    sections = _sections_from_form(form)

    normalized_subdomain = form.get("subdomain", "").strip().lower()
    normalized_theme = form.get("theme_slug", "").strip().lower() or "default"
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

    if not all(
        [
            cleaned_data["subdomain"],
            cleaned_data["full_name"],
            cleaned_data["title_tagline"],
        ]
    ):
        return _render_portfolio_form(
            request,
            user,
            error="Fill in all required portfolio details.",
            form_data=cleaned_data,
            step="details",
        )

    if not cleaned_data["education_text"]:
        return _render_portfolio_form(
            request,
            user,
            error="Education is mandatory.",
            form_data=cleaned_data,
            step="details",
        )

    if not _parse_skills(cleaned_data["skills_text"]):
        return _render_portfolio_form(
            request,
            user,
            error="Add at least one skill.",
            form_data=cleaned_data,
            step="details",
        )

    if not SUBDOMAIN_PATTERN.match(normalized_subdomain):
        return _render_portfolio_form(
            request,
            user,
            error="Subdomain must be 3-63 characters using lowercase letters, numbers, or hyphens.",
            form_data=cleaned_data,
            step="details",
        )

    if normalized_theme not in _theme_slugs():
        return _render_portfolio_form(
            request,
            user,
            error="Choose a valid theme option.",
            form_data=cleaned_data,
            step="details",
        )

    if db.query(Portfolio).filter(Portfolio.subdomain == normalized_subdomain).first() is not None:
        return _render_portfolio_form(
            request,
            user,
            error="That subdomain is already in use.",
            form_data=cleaned_data,
            step="details",
        )

    invalid_project = any(bool(item["title"]) != bool(item["description"]) for item in projects)
    if invalid_project:
        return _render_portfolio_form(
            request,
            user,
            error="Each project needs both a title and description.",
            form_data=cleaned_data,
            step="details",
        )

    valid_projects = [item for item in projects if item["title"] and item["description"]]
    if not valid_projects:
        return _render_portfolio_form(
            request,
            user,
            error="Add at least one project.",
            form_data=cleaned_data,
            step="details",
        )

    invalid_experience = any(
        any(item.values()) and (not item["role"] or not item["company"] or not item["description"])
        for item in experiences
    )
    if invalid_experience:
        return _render_portfolio_form(
            request,
            user,
            error="Each experience entry must include role, company, and description.",
            form_data=cleaned_data,
            step="details",
        )

    valid_experiences = [
        item for item in experiences if item["role"] and item["company"] and item["description"]
    ]

    invalid_certificate = any(
        any(item.values()) and (not item["name"] or not item["issuer"])
        for item in certificates
    )
    if invalid_certificate:
        return _render_portfolio_form(
            request,
            user,
            error="Each certificate entry must include a certificate name and issuer.",
            form_data=cleaned_data,
            step="details",
        )

    valid_certificates = [item for item in certificates if item["name"] and item["issuer"]]
    if not valid_certificates:
        return _render_portfolio_form(
            request,
            user,
            error="Add at least one certificate.",
            form_data=cleaned_data,
            step="details",
        )

    if sections["contact"] and not any(sections["contact_fields"].values()):
        return _render_portfolio_form(
            request,
            user,
            error="Select at least one contact field when Contact Information is enabled.",
            form_data=cleaned_data,
            step="details",
        )

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
            return _render_portfolio_form(
                request,
                user,
                error="Fill in each enabled contact field.",
                form_data=cleaned_data,
                step="details",
            )

    portfolio = Portfolio(
        user_id=user.id,
        subdomain=normalized_subdomain,
        theme_slug=normalized_theme,
        full_name=cleaned_data["full_name"],
        title_tagline=cleaned_data["title_tagline"],
        bio=cleaned_data["bio"],
        section_config=json.dumps(sections),
        education_text=cleaned_data["education_text"],
        skills_text=cleaned_data["skills_text"],
        experiences_json=json.dumps(valid_experiences if sections["experience"] else []),
        certificates_json=json.dumps(valid_certificates),
        contact_data=json.dumps(
            {
                key: cleaned_data[key]
                for key in (
                    "github_url",
                    "leetcode_url",
                    "linkedin_url",
                    "contact_email",
                    "phone_number",
                )
                if sections["contact"]
                and (
                    (key == "github_url" and sections["contact_fields"]["github"])
                    or (key == "leetcode_url" and sections["contact_fields"]["leetcode"])
                    or (key == "linkedin_url" and sections["contact_fields"]["linkedin"])
                    or (key == "contact_email" and sections["contact_fields"]["email"])
                    or (key == "phone_number" and sections["contact_fields"]["phone"])
                )
            }
        ),
        is_published=cleaned_data["is_published"],
    )
    db.add(portfolio)
    db.flush()

    for index, item in enumerate(valid_projects):
        db.add(
            Project(
                portfolio_id=portfolio.id,
                title=item["title"],
                description=item["description"],
                live_url=item["live_url"] or None,
                display_order=index,
            )
        )

    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
