from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from app.api.deps import enforce_csrf, get_owned_portfolio, get_session_user
from app.database import get_db
from app.models import Portfolio, User
from app.schemas.portfolio import PortfolioResponse, PortfolioUpdatePayload, SectionOrderPayload
from app.services.portfolio_service import (
    load_primary_portfolio,
    persist_portfolio,
    serialize_portfolio,
    update_section_order,
    validate_portfolio_payload,
)
from app.services.resume_service import build_resume_pdf


router = APIRouter(tags=["portfolios"])


@router.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/portfolios/{subdomain}", response_model=PortfolioResponse, summary="Fetch a published portfolio")
def get_published_portfolio(subdomain: str, db: Session = Depends(get_db)) -> dict:
    portfolio = (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.subdomain == subdomain.lower(), Portfolio.is_published.is_(True))
        .first()
    )
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published portfolio not found.")
    return serialize_portfolio(portfolio, db)


@router.get("/portfolio", response_model=PortfolioResponse, summary="Fetch the current user's portfolio")
def get_current_user_portfolio(
    user: User = Depends(get_session_user),
    db: Session = Depends(get_db),
) -> dict:
    portfolio = load_primary_portfolio(db, user.id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")
    return serialize_portfolio(portfolio, db)


@router.put("/portfolios/{portfolio_id}", response_model=PortfolioResponse, summary="Update portfolio")
def update_portfolio_route(
    payload: PortfolioUpdatePayload,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    user: User = Depends(get_session_user),
    db: Session = Depends(get_db),
) -> dict:
    validated = validate_portfolio_payload(db, user, payload.model_dump(), portfolio=portfolio)
    updated = persist_portfolio(db, validated, portfolio=portfolio)
    return serialize_portfolio(updated, db)


@router.post("/portfolios/{portfolio_id}/section-order", response_model=PortfolioResponse)
def update_section_order_route(
    payload: SectionOrderPayload,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    updated = update_section_order(db, portfolio, payload.section_order)
    updated = (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.id == updated.id)
        .first()
    )
    return serialize_portfolio(updated, db)


@router.get("/portfolios/{portfolio_id}/resume.pdf", summary="Download ATS-friendly resume PDF")
def download_resume_pdf(
    portfolio: Portfolio = Depends(get_owned_portfolio),
) -> Response:
    pdf_bytes = build_resume_pdf(portfolio)
    filename = f"{portfolio.subdomain}-resume.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
