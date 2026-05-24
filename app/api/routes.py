import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Portfolio, Project, User


router = APIRouter(prefix="/api", tags=["api"])


class ProjectPayload(BaseModel):
    title: str
    description: str
    live_url: str | None = None


class PortfolioUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subdomain: str
    theme_slug: str
    full_name: str
    title_tagline: str
    bio: str = ""
    section_config: dict = Field(default_factory=dict)
    education_text: str
    skills_text: str
    experiences: list[dict] = Field(default_factory=list)
    certificates: list[dict]
    contact_data: dict = Field(default_factory=dict)
    is_published: bool = False
    projects: list[ProjectPayload]


def _serialize_portfolio(portfolio: Portfolio) -> dict:
    try:
        section_config = json.loads(portfolio.section_config or "{}")
    except json.JSONDecodeError:
        section_config = {}
    try:
        experiences = json.loads(portfolio.experiences_json or "[]")
    except json.JSONDecodeError:
        experiences = []
    try:
        certificates = json.loads(portfolio.certificates_json or "[]")
    except json.JSONDecodeError:
        certificates = []
    try:
        contact_data = json.loads(portfolio.contact_data or "{}")
    except json.JSONDecodeError:
        contact_data = {}

    return {
        "id": portfolio.id,
        "subdomain": portfolio.subdomain,
        "theme_slug": portfolio.theme_slug,
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
        "section_config": section_config,
        "education_text": portfolio.education_text,
        "skills_text": portfolio.skills_text,
        "experiences": experiences,
        "certificates": certificates,
        "contact_data": contact_data,
        "is_published": portfolio.is_published,
        "projects": [
            {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "live_url": project.live_url,
                "display_order": project.display_order,
            }
            for project in portfolio.projects
        ],
    }


def _get_session_user(request: Request, db: Session) -> User:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


@router.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/portfolios/{subdomain}", summary="Fetch a published portfolio")
def get_published_portfolio(subdomain: str, db: Session = Depends(get_db)) -> dict:
    portfolio = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.subdomain == subdomain.lower(), Portfolio.is_published.is_(True))
        .first()
    )
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published portfolio not found.",
        )

    return _serialize_portfolio(portfolio)


@router.get("/portfolio", summary="Fetch the current user's portfolio")
def get_current_user_portfolio(request: Request, db: Session = Depends(get_db)) -> dict:
    user = _get_session_user(request, db)
    portfolio = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.user_id == user.id)
        .order_by(Portfolio.id.asc())
        .first()
    )
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )
    return _serialize_portfolio(portfolio)


@router.put("/portfolios/{portfolio_id}", summary="Edit an existing portfolio")
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdatePayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user = _get_session_user(request, db)
    portfolio = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.projects))
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
        .first()
    )
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    normalized_subdomain = payload.subdomain.strip().lower()
    if not normalized_subdomain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomain is required.",
        )

    duplicate = (
        db.query(Portfolio)
        .filter(Portfolio.subdomain == normalized_subdomain, Portfolio.id != portfolio.id)
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That subdomain is already in use.",
        )

    if not payload.projects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one project is required.",
        )

    portfolio.subdomain = normalized_subdomain
    portfolio.theme_slug = payload.theme_slug
    portfolio.full_name = payload.full_name.strip()
    portfolio.title_tagline = payload.title_tagline.strip()
    portfolio.bio = payload.bio.strip()
    portfolio.section_config = json.dumps(payload.section_config)
    portfolio.education_text = payload.education_text.strip()
    portfolio.skills_text = payload.skills_text.strip()
    portfolio.experiences_json = json.dumps(payload.experiences)
    portfolio.certificates_json = json.dumps(payload.certificates)
    portfolio.contact_data = json.dumps(payload.contact_data)
    portfolio.is_published = payload.is_published
    portfolio.projects = [
        Project(
            title=project.title.strip(),
            description=project.description.strip(),
            live_url=(project.live_url or "").strip() or None,
            display_order=index,
        )
        for index, project in enumerate(payload.projects)
    ]

    db.commit()
    db.refresh(portfolio)
    return _serialize_portfolio(portfolio)
