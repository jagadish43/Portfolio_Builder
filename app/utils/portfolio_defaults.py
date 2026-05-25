from __future__ import annotations

import re
from typing import Any


SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
SECTION_SEQUENCE = [
    "about",
    "skills",
    "education",
    "projects",
    "experience",
    "certificates",
    "contact",
]
CONTACT_FIELDS = ("github", "leetcode", "linkedin", "email", "phone")
DEFAULT_THEME_SLUG = "modern"
THEME_SLUGS = ("modern", "minimal", "developer", "creative")
FONT_OPTIONS = (
    "Space Grotesk",
    "IBM Plex Sans",
    "DM Sans",
    "Manrope",
)
DEFAULT_EDUCATION_TYPES = (
    "School",
    "PUC / Intermediate",
    "Diploma",
    "Degree",
    "Masters",
    "PhD",
    "Certification Program",
    "Bootcamp",
    "Custom",
)
DEFAULT_SKILL_CATEGORIES = (
    "Languages",
    "Frameworks",
    "Frontend",
    "Backend",
    "Databases",
    "Tools",
    "Cloud",
    "DevOps",
    "Testing",
    "AI/ML",
    "Libraries",
    "Platforms",
)


def default_section_order() -> list[str]:
    return list(SECTION_SEQUENCE)


def default_theme_config() -> dict[str, Any]:
    return {
        "primary_color": "#0f766e",
        "accent_color": "#f97316",
        "background_color": "#f8fafc",
        "surface_color": "#ffffff",
        "text_color": "#0f172a",
        "font_family": "Space Grotesk",
        "mode": "light",
    }


def default_education_entry() -> dict[str, str]:
    return {
        "education_type": "Degree",
        "custom_type": "",
        "institution_name": "",
        "course_name": "",
        "university": "",
        "specialization": "",
        "start_year": "",
        "end_year": "",
        "score": "",
        "location": "",
        "description": "",
    }


def default_skill_category() -> dict[str, Any]:
    return {
        "category_name": "Languages",
        "skills": [],
    }


def normalize_theme_slug(theme_slug: str | None) -> str:
    normalized = (theme_slug or "").strip().lower()
    return normalized if normalized in THEME_SLUGS else DEFAULT_THEME_SLUG


def normalize_section_order(raw: list[str] | None) -> list[str]:
    allowed = {section for section in SECTION_SEQUENCE}
    ordered = [item for item in raw or [] if item in allowed]
    seen: set[str] = set()
    normalized: list[str] = []
    for item in ordered:
        if item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    for item in SECTION_SEQUENCE:
        if item not in seen:
            normalized.append(item)
    return normalized


def normalize_section_config(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = raw or {}
    contact_fields = payload.get("contact_fields", {})
    return {
        "about": True,
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


def parse_skills(raw: str | None, bio: str = "") -> list[str]:
    source = (raw or "").strip()
    if source:
        tokens = re.split(r"[\n,]", source)
        return [token.strip() for token in tokens if token.strip()]
    for line in bio.splitlines():
        normalized_line = line.strip()
        if normalized_line.lower().startswith("skills:"):
            _, raw_skills = normalized_line.split(":", maxsplit=1)
            return [skill.strip() for skill in raw_skills.split(",") if skill.strip()]
    return []
