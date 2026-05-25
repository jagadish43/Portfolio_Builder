from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Portfolio.id",
    )
    oauth_connections: Mapped[list["OAuthConnection"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Portfolio(TimestampMixin, Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        Index("ix_portfolios_subdomain", "subdomain", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subdomain: Mapped[str] = mapped_column(String(63), nullable=False)
    theme_slug: Mapped[str] = mapped_column(String(100), nullable=False, default="modern")
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title_tagline: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    section_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    section_order: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default='["about","skills","education","projects","experience","certificates","contact"]',
    )
    theme_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    education_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    skills_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    experiences_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    certificates_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    contact_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship(back_populates="portfolios")
    projects: Mapped[list["Project"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="Project.display_order",
    )
    analytics_events: Mapped[list["AnalyticsEvent"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    custom_domains: Mapped[list["CustomDomain"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="CustomDomain.created_at.desc()",
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="Deployment.created_at.desc()",
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    live_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tech_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="projects")


class AnalyticsEvent(TimestampMixin, Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_portfolio_created_at", "portfolio_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    project_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visitor_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    portfolio: Mapped["Portfolio"] = relationship(back_populates="analytics_events")


class CustomDomain(TimestampMixin, Base):
    __tablename__ = "custom_domains"
    __table_args__ = (
        Index("ix_custom_domains_domain", "domain", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    verification_token: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="vercel")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="custom_domains")


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_portfolio_created_at", "portfolio_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="vercel")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    deployment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    build_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="deployments")


class OAuthConnection(TimestampMixin, Base):
    __tablename__ = "oauth_connections"
    __table_args__ = (
        Index("ix_oauth_connections_user_provider", "user_id", "provider", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    user: Mapped["User"] = relationship(back_populates="oauth_connections")
