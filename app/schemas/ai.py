from pydantic import BaseModel, ConfigDict


class AIEnhancementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: str
    text: str
    concise: bool = False


class AIEnhancementResponse(BaseModel):
    content_type: str
    original_text: str
    enhanced_text: str
    provider: str
    used_fallback: bool = False
