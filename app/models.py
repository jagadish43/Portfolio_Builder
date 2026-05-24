from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Portfolio.id",
    )


class Portfolio(Base):
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
    theme_slug: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title_tagline: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    section_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    education_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    live_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="projects")
