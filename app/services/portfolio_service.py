from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models import CustomDomain, Deployment, Portfolio, Project, User
from app.services.analytics_service import build_summary
from app.services.template_service import build_template_preview
from app.utils.json_tools import dump_json, parse_json_list, parse_json_object, parse_json_string_list
from app.utils.portfolio_defaults import (
    CONTACT_FIELDS,
    SUBDOMAIN_PATTERN,
    DEFAULT_EDUCATION_TYPES,
    DEFAULT_SKILL_CATEGORIES,
    default_section_order,
    default_education_entry,
    default_skill_category,
    default_theme_config,
    normalize_section_config,
    normalize_section_order,
    normalize_theme_slug,
    parse_skills,
)


def load_portfolio_for_user(db: Session, user_id: int, portfolio_id: int) -> Portfolio | None:
    return (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
        .first()
    )


def load_primary_portfolio(db: Session, user_id: int) -> Portfolio | None:
    return (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.user_id == user_id)
        .order_by(Portfolio.id.asc())
        .first()
    )


def load_user_portfolios(db: Session, user_id: int) -> list[Portfolio]:
    return (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.user_id == user_id)
        .order_by(Portfolio.id.asc())
        .all()
    )


def build_contact_visibility(contact_data: dict[str, Any], sections: dict[str, Any]) -> dict[str, bool]:
    return {
        "contact": bool(contact_data.get("display_contact", sections["contact"])),
        "github": bool(contact_data.get("display_github", sections["contact_fields"]["github"])),
        "leetcode": bool(contact_data.get("display_leetcode", sections["contact_fields"]["leetcode"])),
        "linkedin": bool(contact_data.get("display_linkedin", sections["contact_fields"]["linkedin"])),
        "email": bool(contact_data.get("display_email", sections["contact_fields"]["email"])),
        "phone": bool(contact_data.get("display_phone", sections["contact_fields"]["phone"])),
        "resume": bool(contact_data.get("display_resume", bool(contact_data.get("resume_url")))),
    }


def normalize_education_entries(raw_entries: list[dict[str, Any]] | None, legacy_text: str | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw in raw_entries or []:
        entry = default_education_entry()
        entry.update({key: str(raw.get(key, "")).strip() for key in entry})
        if entry["education_type"] == "Custom" and not entry["custom_type"]:
            entry["custom_type"] = "Custom Education"
        if entry["institution_name"] or entry["course_name"]:
            entries.append(entry)
    if entries:
        return entries
    if legacy_text and legacy_text.strip():
        entry = default_education_entry()
        entry["education_type"] = "Degree"
        entry["institution_name"] = legacy_text.strip().split(",")[0][:255]
        entry["description"] = legacy_text.strip()
        return [entry]
    return []


def education_entries_to_text(entries: list[dict[str, str]]) -> str:
    lines = []
    for entry in entries:
        title = entry["custom_type"] if entry["education_type"] == "Custom" else entry["education_type"]
        primary = " - ".join(part for part in [entry["course_name"], entry["specialization"]] if part)
        institution = ", ".join(part for part in [entry["institution_name"], entry["university"]] if part)
        years = " - ".join(part for part in [entry["start_year"], entry["end_year"]] if part)
        summary = " | ".join(part for part in [title, primary, institution, years, entry["score"]] if part)
        lines.append(summary or entry["description"])
    return "\n".join(line for line in lines if line)


def normalize_skill_categories(raw_categories: list[dict[str, Any]] | None, legacy_text: str | None = None) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    for raw in raw_categories or []:
        category_name = str(raw.get("category_name", "")).strip()
        if not category_name:
            continue
        seen: set[str] = set()
        skills: list[str] = []
        for raw_skill in raw.get("skills", []) or []:
            skill = str(raw_skill).strip()
            normalized = skill.lower()
            if not skill or normalized in seen:
                continue
            seen.add(normalized)
            skills.append(skill)
        if skills:
            categories.append({"category_name": category_name, "skills": skills})
    if categories:
        return categories
    legacy_skills = parse_skills(legacy_text or "")
    if legacy_skills:
        return [{"category_name": "Languages", "skills": legacy_skills}]
    return []


def skill_categories_to_text(categories: list[dict[str, Any]]) -> str:
    return ", ".join(
        skill
        for category in categories
        for skill in category.get("skills", [])
    )


def deserialize_portfolio(portfolio: Portfolio) -> dict[str, Any]:
    section_config = normalize_section_config(parse_json_object(portfolio.section_config))
    section_order = normalize_section_order(parse_json_string_list(portfolio.section_order))
    theme_config = {**default_theme_config(), **parse_json_object(portfolio.theme_config)}
    experiences = parse_json_list(portfolio.experiences_json)
    certificates = parse_json_list(portfolio.certificates_json)
    contact_data = parse_json_object(portfolio.contact_data)
    education_entries = normalize_education_entries(parse_json_list(portfolio.education_json), portfolio.education_text)
    skill_categories = normalize_skill_categories(parse_json_list(portfolio.skills_json), portfolio.skills_text)
    skills = [skill for category in skill_categories for skill in category.get("skills", [])]
    contact_visibility = build_contact_visibility(contact_data, section_config)

    ordered_sections = []
    for key in section_order:
        if key == "about" and portfolio.bio:
            ordered_sections.append({"key": "about", "title": "About"})
        if key == "skills" and skill_categories:
            ordered_sections.append({"key": "skills", "title": "Skills"})
        if key == "education" and education_entries:
            ordered_sections.append({"key": "education", "title": "Education"})
        if key == "projects" and portfolio.projects:
            ordered_sections.append({"key": "projects", "title": "Projects"})
        if key == "experience" and section_config["experience"] and experiences:
            ordered_sections.append({"key": "experience", "title": "Experience"})
        if key == "certificates" and certificates:
            ordered_sections.append({"key": "certificates", "title": "Certificates"})
        if key == "contact" and section_config["contact"]:
            ordered_sections.append({"key": "contact", "title": "Contact"})

    return {
        "section_config": section_config,
        "section_order": section_order,
        "ordered_sections": ordered_sections,
        "theme_config": theme_config,
        "education_text": portfolio.education_text or education_entries_to_text(education_entries),
        "education_entries": education_entries,
        "education_type_options": list(DEFAULT_EDUCATION_TYPES),
        "skills": skills,
        "skill_categories": skill_categories,
        "skill_category_options": list(DEFAULT_SKILL_CATEGORIES),
        "experiences": experiences,
        "certificates": certificates,
        "contact_data": contact_data,
        "contact_visibility": contact_visibility,
        "contact_items": [
            ("GitHub", contact_data.get("github_url", ""), contact_visibility["github"]),
            ("LeetCode", contact_data.get("leetcode_url", ""), contact_visibility["leetcode"]),
            ("LinkedIn", contact_data.get("linkedin_url", ""), contact_visibility["linkedin"]),
            ("Email", contact_data.get("contact_email", ""), contact_visibility["email"]),
            ("Phone", contact_data.get("phone_number", ""), contact_visibility["phone"]),
        ],
        "resume_url": contact_data.get("resume_url", ""),
    }


def serialize_portfolio(portfolio: Portfolio, db: Session | None = None) -> dict[str, Any]:
    details = deserialize_portfolio(portfolio)
    analytics_snapshot = build_summary(db, portfolio.id, 7) if db is not None else {}
    return {
        "id": portfolio.id,
        "subdomain": portfolio.subdomain,
        "theme_slug": portfolio.theme_slug,
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
        "section_config": details["section_config"],
        "section_order": details["section_order"],
        "theme_config": details["theme_config"],
        "education_text": portfolio.education_text,
        "skills_text": portfolio.skills_text,
        "education_entries": details["education_entries"],
        "skill_categories": details["skill_categories"],
        "experiences": details["experiences"],
        "certificates": details["certificates"],
        "contact_data": details["contact_data"],
        "is_published": portfolio.is_published,
        "projects": [
            {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "live_url": project.live_url,
                "github_url": project.github_url,
                "tech_stack": project.tech_stack,
                "stars": project.stars,
                "display_order": project.display_order,
            }
            for project in portfolio.projects
        ],
        "analytics_snapshot": analytics_snapshot,
        "domains": [serialize_domain(item) for item in getattr(portfolio, "custom_domains", [])],
        "deployments": [serialize_deployment(item) for item in getattr(portfolio, "deployments", [])],
        "template_preview": build_template_preview(portfolio.theme_slug),
    }


def serialize_domain(domain: CustomDomain) -> dict[str, Any]:
    return {
        "id": domain.id,
        "domain": domain.domain,
        "status": domain.status,
        "verification_token": domain.verification_token,
        "provider": domain.provider,
        "verified_at": domain.verified_at.isoformat() if domain.verified_at else None,
    }


def serialize_deployment(deployment: Deployment) -> dict[str, Any]:
    return {
        "id": deployment.id,
        "provider": deployment.provider,
        "status": deployment.status,
        "deployment_url": deployment.deployment_url,
        "external_id": deployment.external_id,
        "created_at": deployment.created_at.isoformat(),
    }


def validate_portfolio_payload(
    db: Session,
    user: User,
    payload: dict[str, Any],
    portfolio: Portfolio | None = None,
) -> dict[str, Any]:
    normalized_subdomain = payload["subdomain"].strip().lower()
    if not normalized_subdomain or not SUBDOMAIN_PATTERN.match(normalized_subdomain):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subdomain must be 3-63 characters using lowercase letters, numbers, or hyphens.",
        )

    duplicate = db.query(Portfolio).filter(Portfolio.subdomain == normalized_subdomain)
    if portfolio is not None:
        duplicate = duplicate.filter(Portfolio.id != portfolio.id)
    if duplicate.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That subdomain is already in use.",
        )

    if not payload["full_name"].strip() or not payload["title_tagline"].strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Full name and title are required.",
        )

    education_entries = normalize_education_entries(payload.get("education_entries"), payload.get("education_text"))
    if not education_entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Education is mandatory.",
        )

    skill_categories = normalize_skill_categories(payload.get("skill_categories"), payload.get("skills_text"))
    if not skill_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one skill.",
        )

    projects = [
        item
        for item in payload["projects"]
        if item["title"].strip() and item["description"].strip()
    ]
    if not projects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one project.",
        )

    certificates = [
        item
        for item in payload["certificates"]
        if item["name"].strip() and item["issuer"].strip()
    ]
    if not certificates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one certificate.",
        )

    section_config = normalize_section_config(payload["section_config"])
    section_order = normalize_section_order(payload["section_order"])
    theme_config = {**default_theme_config(), **payload["theme_config"]}
    theme_slug = normalize_theme_slug(payload["theme_slug"])

    contact_data = dict(payload["contact_data"])
    if section_config["contact"] and not any(section_config["contact_fields"].values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one contact field when contact is enabled.",
        )
    for field in CONTACT_FIELDS:
        enabled = section_config["contact_fields"][field]
        key = {
            "github": "github_url",
            "leetcode": "leetcode_url",
            "linkedin": "linkedin_url",
            "email": "contact_email",
            "phone": "phone_number",
        }[field]
        if enabled and not contact_data.get(key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing value for {field}.",
            )

    return {
        "user": user,
        "subdomain": normalized_subdomain,
        "theme_slug": theme_slug,
        "full_name": payload["full_name"].strip(),
        "title_tagline": payload["title_tagline"].strip(),
        "bio": payload["bio"].strip(),
        "section_config": section_config,
        "section_order": section_order,
        "theme_config": theme_config,
        "education_text": education_entries_to_text(education_entries),
        "education_entries": education_entries,
        "skills_text": skill_categories_to_text(skill_categories),
        "skill_categories": skill_categories,
        "experiences": [
            item for item in payload["experiences"] if item["role"].strip() and item["company"].strip()
        ],
        "certificates": certificates,
        "contact_data": contact_data,
        "is_published": bool(payload["is_published"]),
        "projects": projects,
    }


def persist_portfolio(
    db: Session,
    data: dict[str, Any],
    portfolio: Portfolio | None = None,
) -> Portfolio:
    target = portfolio or Portfolio(user_id=data["user"].id, subdomain=data["subdomain"])
    target.subdomain = data["subdomain"]
    target.theme_slug = data["theme_slug"]
    target.full_name = data["full_name"]
    target.title_tagline = data["title_tagline"]
    target.bio = data["bio"]
    target.section_config = dump_json(data["section_config"])
    target.section_order = dump_json(data["section_order"])
    target.theme_config = dump_json(data["theme_config"])
    target.education_text = data["education_text"]
    target.education_json = dump_json(data["education_entries"])
    target.skills_text = data["skills_text"]
    target.skills_json = dump_json(data["skill_categories"])
    target.experiences_json = dump_json(data["experiences"])
    target.certificates_json = dump_json(data["certificates"])
    target.contact_data = dump_json(data["contact_data"])
    target.is_published = data["is_published"]
    target.projects = [
        Project(
            title=item["title"].strip(),
            description=item["description"].strip(),
            live_url=str(item.get("live_url") or "").strip() or None,
            github_url=str(item.get("github_url") or "").strip() or None,
            tech_stack=str(item.get("tech_stack") or "").strip() or None,
            stars=int(item.get("stars") or 0),
            display_order=index,
        )
        for index, item in enumerate(data["projects"])
    ]
    if portfolio is None:
        db.add(target)
    db.commit()
    db.refresh(target)
    return load_portfolio_for_user(db, data["user"].id, target.id) or target


def update_section_order(db: Session, portfolio: Portfolio, section_order: list[str]) -> Portfolio:
    portfolio.section_order = dump_json(normalize_section_order(section_order))
    db.commit()
    db.refresh(portfolio)
    return portfolio


def default_form_state(user_email: str = "") -> dict[str, Any]:
    return {
        "step": "customize",
        "subdomain": "",
        "full_name": "",
        "title_tagline": "",
        "bio": "",
        "theme_slug": "modern",
        "is_published": True,
        "education_text": "",
        "skills_text": "",
        "education_entries": [default_education_entry()],
        "skill_categories": [default_skill_category()],
        "github_url": "",
        "leetcode_url": "",
        "linkedin_url": "",
        "contact_email": user_email,
        "phone_number": "",
        "resume_url": "",
        "sections": normalize_section_config(),
        "section_order": default_section_order(),
        "theme_config": default_theme_config(),
        "projects": [{"title": "", "description": "", "live_url": "", "github_url": "", "tech_stack": ""}],
        "experiences": [{"role": "", "company": "", "duration": "", "description": ""}],
        "certificates": [{"name": "", "issuer": "", "year": "", "url": ""}],
    }
