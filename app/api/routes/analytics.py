from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_owned_portfolio
from app.database import get_db
from app.models import Portfolio
from app.schemas.analytics import AnalyticsSummaryResponse, AnalyticsTrackRequest
from app.services.analytics_service import build_summary, serialize_event, track_event


router = APIRouter(tags=["analytics"])


@router.post("/analytics/track", summary="Track a public portfolio event")
def track_public_event(
    payload: AnalyticsTrackRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.subdomain == payload.subdomain.lower(), Portfolio.is_published.is_(True))
        .first()
    )
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")
    event = track_event(
        db,
        portfolio,
        payload.event_type,
        request,
        source=payload.source,
        project_slug=payload.project_slug,
        metadata=payload.metadata,
    )
    return {"status": "ok", "event": serialize_event(event)}


@router.get("/portfolios/{portfolio_id}/analytics", response_model=AnalyticsSummaryResponse)
def get_portfolio_analytics(
    days: int = 7,
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    return build_summary(db, portfolio.id, 30 if days >= 30 else 7)
