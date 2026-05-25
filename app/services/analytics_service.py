from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalyticsEvent, Portfolio
from app.utils.json_tools import dump_json, parse_json_object


TRACKABLE_EVENTS = {"visit", "project_click", "resume_download"}


def _device_type(user_agent: str) -> str:
    normalized = user_agent.lower()
    if "mobile" in normalized:
        return "mobile"
    if "tablet" in normalized or "ipad" in normalized:
        return "tablet"
    return "desktop"


def build_visitor_hash(request: Request) -> str:
    settings = get_settings()
    seed = "|".join(
        [
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", ""),
            settings.analytics_salt,
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def track_event(
    db: Session,
    portfolio: Portfolio,
    event_type: str,
    request: Request,
    source: str | None = None,
    project_slug: str | None = None,
    metadata: dict | None = None,
) -> AnalyticsEvent:
    event = AnalyticsEvent(
        portfolio_id=portfolio.id,
        event_type=event_type if event_type in TRACKABLE_EVENTS else "visit",
        source=source or request.headers.get("referer") or "direct",
        device_type=_device_type(request.headers.get("user-agent", "")),
        project_slug=project_slug,
        visitor_hash=build_visitor_hash(request),
        metadata_json=dump_json(metadata or {}),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def build_summary(db: Session, portfolio_id: int, days: int = 7) -> dict:
    start = datetime.utcnow() - timedelta(days=max(days, 1) - 1)
    events = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.portfolio_id == portfolio_id, AnalyticsEvent.created_at >= start)
        .order_by(AnalyticsEvent.created_at.asc())
        .all()
    )

    totals = Counter(event.event_type for event in events)
    visitors = {event.visitor_hash for event in events if event.visitor_hash}
    daily_map: dict[str, Counter] = defaultdict(Counter)
    project_counter = Counter(
        event.project_slug for event in events if event.event_type == "project_click" and event.project_slug
    )
    source_counter = Counter(event.source or "direct" for event in events)
    device_counter = Counter(event.device_type or "desktop" for event in events)

    for event in events:
        key = event.created_at.strftime("%Y-%m-%d")
        daily_map[key][event.event_type] += 1

    daily = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        counts = daily_map.get(day, Counter())
        daily.append(
            {
                "date": day,
                "visits": counts.get("visit", 0),
                "project_clicks": counts.get("project_click", 0),
                "resume_downloads": counts.get("resume_download", 0),
            }
        )

    return {
        "portfolio_id": portfolio_id,
        "days": days,
        "totals": {
            "visits": totals.get("visit", 0),
            "unique_visitors": len(visitors),
            "project_clicks": totals.get("project_click", 0),
            "resume_downloads": totals.get("resume_download", 0),
        },
        "daily": daily,
        "top_projects": [
            {"project_slug": key, "clicks": value} for key, value in project_counter.most_common(5)
        ],
        "sources": [{"source": key, "count": value} for key, value in source_counter.most_common(5)],
        "devices": [{"device_type": key, "count": value} for key, value in device_counter.most_common()],
    }


def serialize_event(event: AnalyticsEvent) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "source": event.source,
        "device_type": event.device_type,
        "project_slug": event.project_slug,
        "metadata": parse_json_object(event.metadata_json),
        "created_at": event.created_at.isoformat(),
    }
