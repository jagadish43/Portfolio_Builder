from fastapi import APIRouter

from app.api.routes.ai import router as ai_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.portfolios import router as portfolios_router


router = APIRouter(prefix="/api")
router.include_router(portfolios_router)
router.include_router(ai_router)
router.include_router(analytics_router)
router.include_router(integrations_router)
