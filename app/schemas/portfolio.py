from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.utils.portfolio_defaults import default_section_order, default_theme_config


class ProjectPayload(BaseModel):
    title: str
    description: str
    live_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    tech_stack: str | None = None
    stars: int = 0


class ExperiencePayload(BaseModel):
    role: str
    company: str
    duration: str = ""
    description: str


class CertificatePayload(BaseModel):
    name: str
    issuer: str
    year: str = ""
    url: HttpUrl | None = None


class ThemeConfigPayload(BaseModel):
    primary_color: str = "#0f766e"
    accent_color: str = "#f97316"
    background_color: str = "#f8fafc"
    surface_color: str = "#ffffff"
    text_color: str = "#0f172a"
    font_family: str = "Space Grotesk"
    mode: str = "light"


class EducationPayload(BaseModel):
    education_type: str
    custom_type: str = ""
    institution_name: str
    course_name: str
    university: str = ""
    specialization: str = ""
    start_year: str = ""
    end_year: str = ""
    score: str = ""
    location: str = ""
    description: str = ""


class SkillCategoryPayload(BaseModel):
    category_name: str
    skills: list[str] = Field(default_factory=list)


class PortfolioUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subdomain: str
    theme_slug: str
    full_name: str
    title_tagline: str
    bio: str = ""
    section_config: dict[str, Any] = Field(default_factory=dict)
    section_order: list[str] = Field(default_factory=default_section_order)
    theme_config: ThemeConfigPayload = Field(default_factory=ThemeConfigPayload)
    education_text: str
    skills_text: str
    education_entries: list[EducationPayload] = Field(default_factory=list)
    skill_categories: list[SkillCategoryPayload] = Field(default_factory=list)
    experiences: list[ExperiencePayload] = Field(default_factory=list)
    certificates: list[CertificatePayload] = Field(default_factory=list)
    contact_data: dict[str, Any] = Field(default_factory=dict)
    is_published: bool = False
    projects: list[ProjectPayload]


class SectionOrderPayload(BaseModel):
    section_order: list[str] = Field(default_factory=default_section_order)


class PortfolioResponse(BaseModel):
    id: int
    subdomain: str
    theme_slug: str
    full_name: str
    title_tagline: str
    bio: str
    section_config: dict[str, Any]
    section_order: list[str]
    theme_config: dict[str, Any]
    education_text: str | None
    skills_text: str | None
    education_entries: list[dict[str, Any]]
    skill_categories: list[dict[str, Any]]
    experiences: list[dict[str, Any]]
    certificates: list[dict[str, Any]]
    contact_data: dict[str, Any]
    is_published: bool
    projects: list[dict[str, Any]]
    analytics_snapshot: dict[str, Any] = Field(default_factory=dict)
    domains: list[dict[str, Any]] = Field(default_factory=list)
    deployments: list[dict[str, Any]] = Field(default_factory=list)
    template_preview: dict[str, Any] = Field(default_factory=dict)


class DefaultPortfolioFormState(BaseModel):
    step: str = "customize"
    subdomain: str = ""
    full_name: str = ""
    title_tagline: str = ""
    bio: str = ""
    theme_slug: str = "modern"
    is_published: bool = True
    education_text: str = ""
    skills_text: str = ""
    education_entries: list[dict[str, Any]] = Field(default_factory=list)
    skill_categories: list[dict[str, Any]] = Field(default_factory=list)
    github_url: str = ""
    leetcode_url: str = ""
    linkedin_url: str = ""
    contact_email: str = ""
    phone_number: str = ""
    resume_url: str = ""
    sections: dict[str, Any] = Field(default_factory=lambda: {
        "about": True,
        "education": True,
        "projects": True,
        "experience": False,
        "skills": True,
        "certificates": True,
        "contact": False,
        "contact_fields": {
            "github": False,
            "leetcode": False,
            "linkedin": False,
            "email": False,
            "phone": False,
        },
    })
    section_order: list[str] = Field(default_factory=default_section_order)
    theme_config: dict[str, Any] = Field(default_factory=default_theme_config)
    projects: list[dict[str, str]] = Field(
        default_factory=lambda: [{"title": "", "description": "", "live_url": "", "github_url": "", "tech_stack": ""}]
    )
    experiences: list[dict[str, str]] = Field(
        default_factory=lambda: [{"role": "", "company": "", "duration": "", "description": ""}]
    )
    certificates: list[dict[str, str]] = Field(
        default_factory=lambda: [{"name": "", "issuer": "", "year": "", "url": ""}]
    )
