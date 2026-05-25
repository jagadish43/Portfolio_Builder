from __future__ import annotations

import secrets
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CustomDomain, Deployment, OAuthConnection, Portfolio, Project, User
from app.utils.json_tools import dump_json


def create_or_update_custom_domain(db: Session, portfolio: Portfolio, domain: str) -> CustomDomain:
    normalized = domain.strip().lower()
    existing = (
        db.query(CustomDomain)
        .filter(CustomDomain.portfolio_id == portfolio.id, CustomDomain.domain == normalized)
        .first()
    )
    target = existing or CustomDomain(
        portfolio_id=portfolio.id,
        domain=normalized,
        verification_token=secrets.token_urlsafe(24),
    )
    target.status = "pending"
    if existing is None:
        db.add(target)
    db.commit()
    db.refresh(target)
    return target


async def verify_domain_with_vercel(domain: CustomDomain) -> dict:
    settings = get_settings()
    if not settings.vercel_api_token:
        return {
            "status": "pending",
            "instructions": [
                {
                    "type": "TXT",
                    "name": f"_portfolio-builder.{domain.domain}",
                    "value": domain.verification_token,
                }
            ],
        }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.vercel.com/v10/projects/domains",
            params={"teamId": settings.vercel_team_id} if settings.vercel_team_id else None,
            headers={"Authorization": f"Bearer {settings.vercel_api_token}"},
            json={"name": domain.domain},
        )
        response.raise_for_status()
        return response.json()


def create_deployment(db: Session, portfolio: Portfolio) -> Deployment:
    deployment = Deployment(portfolio_id=portfolio.id, status="queued")
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


async def deploy_to_vercel(portfolio: Portfolio, deployment: Deployment) -> dict:
    settings = get_settings()
    if not settings.vercel_api_token:
        return {
            "status": "queued",
            "deployment_url": None,
            "external_id": None,
            "build_log": "Vercel credentials not configured. Deployment queued locally.",
        }

    files = [
        {
            "file": "index.html",
            "data": f"<html><body><h1>{portfolio.full_name}</h1><p>{portfolio.title_tagline}</p></body></html>",
        }
    ]
    payload = {"name": f"portfolio-{portfolio.subdomain}", "files": files, "project": settings.vercel_project_id}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.vercel.com/v13/deployments",
            params={"teamId": settings.vercel_team_id} if settings.vercel_team_id else None,
            headers={"Authorization": f"Bearer {settings.vercel_api_token}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    return {
        "status": data.get("readyState", "queued"),
        "deployment_url": data.get("url"),
        "external_id": data.get("id"),
        "build_log": dump_json(data),
    }


async def import_github_repositories(username: str, repository_names: list[str]) -> list[dict]:
    settings = get_settings()
    headers = {}
    if settings.github_personal_access_token:
        headers["Authorization"] = f"Bearer {settings.github_personal_access_token}"
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        imported: list[dict] = []
        for repository_name in repository_names:
            response = await client.get(f"https://api.github.com/repos/{username}/{repository_name}")
            response.raise_for_status()
            repo = response.json()
            imported.append(
                {
                    "title": repo["name"],
                    "description": repo.get("description") or "Imported from GitHub.",
                    "live_url": repo.get("homepage") or repo.get("html_url"),
                    "github_url": repo.get("html_url"),
                    "tech_stack": repo.get("language") or "",
                    "stars": int(repo.get("stargazers_count") or 0),
                }
            )
        return imported


def upsert_oauth_connection(
    db: Session,
    user: User,
    provider: str,
    access_token: str | None = None,
    refresh_token: str | None = None,
    external_user_id: str | None = None,
    profile_json: str = "{}",
) -> OAuthConnection:
    connection = (
        db.query(OAuthConnection)
        .filter(OAuthConnection.user_id == user.id, OAuthConnection.provider == provider)
        .first()
    )
    target = connection or OAuthConnection(user_id=user.id, provider=provider)
    target.access_token = access_token
    target.refresh_token = refresh_token
    target.external_user_id = external_user_id
    target.profile_json = profile_json
    target.updated_at = datetime.utcnow()
    if connection is None:
        db.add(target)
    db.commit()
    db.refresh(target)
    return target


def import_linkedin_payload(portfolio: Portfolio, payload: dict) -> dict:
    portfolio.full_name = payload.get("full_name") or portfolio.full_name
    portfolio.title_tagline = payload.get("headline") or portfolio.title_tagline
    portfolio.bio = payload.get("bio") or portfolio.bio
    portfolio.education_text = payload.get("education_text") or portfolio.education_text
    skills = payload.get("skills") or []
    if skills:
        portfolio.skills_text = ", ".join(str(skill) for skill in skills)
    return {
        "full_name": portfolio.full_name,
        "title_tagline": portfolio.title_tagline,
        "bio": portfolio.bio,
        "education_text": portfolio.education_text,
        "skills_text": portfolio.skills_text,
        "experiences": payload.get("experiences") or [],
    }


def replace_projects_from_import(portfolio: Portfolio, projects: list[dict]) -> None:
    portfolio.projects = [
        Project(
            title=item["title"],
            description=item["description"],
            live_url=item.get("live_url"),
            github_url=item.get("github_url"),
            tech_stack=item.get("tech_stack"),
            stars=int(item.get("stars") or 0),
            display_order=index,
        )
        for index, item in enumerate(projects)
    ]
