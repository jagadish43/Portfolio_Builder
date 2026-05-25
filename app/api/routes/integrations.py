from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app.api.deps import enforce_csrf, get_owned_portfolio, get_session_user
from app.database import get_db
from app.models import Portfolio, User
from app.schemas.integrations import (
    CustomDomainRequest,
    DeployRequest,
    GitHubImportRequest,
    LinkedInImportRequest,
)
from app.services.integration_service import (
    create_deployment,
    create_or_update_custom_domain,
    deploy_to_vercel,
    import_github_repositories,
    import_linkedin_payload,
    replace_projects_from_import,
    verify_domain_with_vercel,
)
from app.services.portfolio_service import serialize_portfolio
from app.utils.json_tools import dump_json


router = APIRouter(tags=["integrations"])


@router.post("/portfolios/{portfolio_id}/domains", summary="Attach a custom domain")
async def attach_custom_domain(
    payload: CustomDomainRequest,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    domain = create_or_update_custom_domain(db, portfolio, payload.domain)
    verification = await verify_domain_with_vercel(domain)
    domain.status = verification.get("status", "pending")
    if verification.get("status") == "verified":
        from datetime import datetime

        domain.verified_at = datetime.utcnow()
    db.commit()
    db.refresh(domain)
    return {
        "domain": payload.domain,
        "status": domain.status,
        "verification_token": domain.verification_token,
        "verification": verification,
    }


@router.post("/portfolios/{portfolio_id}/deployments", summary="Create a deployment")
async def deploy_portfolio(
    _: DeployRequest,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    deployment = create_deployment(db, portfolio)
    result = await deploy_to_vercel(portfolio, deployment)
    deployment.status = result["status"]
    deployment.deployment_url = result["deployment_url"]
    deployment.external_id = result["external_id"]
    deployment.build_log = result["build_log"]
    db.commit()
    db.refresh(deployment)
    return {
        "status": deployment.status,
        "deployment_url": deployment.deployment_url,
        "deployment_id": deployment.id,
        "external_id": deployment.external_id,
    }


@router.post("/portfolios/{portfolio_id}/github-import", summary="Import repositories from GitHub")
async def github_import(
    payload: GitHubImportRequest,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    projects = await import_github_repositories(payload.username, payload.repository_names)
    replace_projects_from_import(portfolio, projects)
    db.commit()
    reloaded = (
        db.query(Portfolio)
        .options(
            selectinload(Portfolio.projects),
            selectinload(Portfolio.custom_domains),
            selectinload(Portfolio.deployments),
        )
        .filter(Portfolio.id == portfolio.id)
        .first()
    )
    return {"imported_count": len(projects), "portfolio": serialize_portfolio(reloaded, db)}


@router.post("/portfolios/{portfolio_id}/linkedin-import", summary="Import profile data from LinkedIn fallback payload")
def linkedin_import(
    payload: LinkedInImportRequest,
    _csrf: None = Depends(enforce_csrf),
    portfolio: Portfolio = Depends(get_owned_portfolio),
    db: Session = Depends(get_db),
) -> dict:
    imported = import_linkedin_payload(portfolio, payload.model_dump())
    portfolio.experiences_json = dump_json(payload.experiences)
    db.commit()
    db.refresh(portfolio)
    return {"status": "ok", "imported": imported}


@router.get("/integrations/status", summary="List enabled integration connections")
def integration_status(
    user: User = Depends(get_session_user),
    db: Session = Depends(get_db),
) -> dict:
    return {
        "user_id": user.id,
        "connections": [
            {
                "provider": connection.provider,
                "external_user_id": connection.external_user_id,
                "updated_at": connection.updated_at.isoformat(),
            }
            for connection in user.oauth_connections
        ],
    }
