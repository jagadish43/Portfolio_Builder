from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Portfolio


router = APIRouter(prefix="/api", tags=["api"])


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

    return {
        "id": portfolio.id,
        "subdomain": portfolio.subdomain,
        "theme_slug": portfolio.theme_slug,
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
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
