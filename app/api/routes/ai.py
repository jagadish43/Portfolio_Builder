from fastapi import APIRouter, Depends

from app.api.deps import enforce_csrf, get_session_user
from app.models import User
from app.schemas.ai import AIEnhancementRequest, AIEnhancementResponse
from app.services.ai_service import enhance_text


router = APIRouter(tags=["ai"])


@router.post("/ai/enhance", response_model=AIEnhancementResponse, summary="Enhance content with AI")
async def enhance_content(
    payload: AIEnhancementRequest,
    _csrf: None = Depends(enforce_csrf),
    _user: User = Depends(get_session_user),
) -> dict:
    result = await enhance_text(payload.content_type, payload.text, payload.concise)
    return {
        "content_type": payload.content_type,
        "original_text": payload.text,
        **result,
    }
