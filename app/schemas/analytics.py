from pydantic import BaseModel, ConfigDict, Field


class AnalyticsTrackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subdomain: str
    event_type: str
    project_slug: str | None = None
    source: str | None = None
    metadata: dict = Field(default_factory=dict)


class AnalyticsSummaryResponse(BaseModel):
    portfolio_id: int
    days: int
    totals: dict
    daily: list[dict]
    top_projects: list[dict]
    sources: list[dict]
    devices: list[dict]
