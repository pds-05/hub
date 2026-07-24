from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.services.ai_assistant import AIAssistantService, get_ai_assistant_service

router = APIRouter(prefix="/assistant", tags=["ai assistant"])


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    context: dict = Field(default_factory=dict)


@router.post("/analyze")
async def analyze_incident(
    payload: AnalyzeRequest,
    service: AIAssistantService = Depends(get_ai_assistant_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ = current_user
    return await service.analyze_incident(payload.question, payload.context)
