from fastapi import APIRouter, Depends, Query

from agent.conversations import list_conversations
from core.auth import CurrentUser, get_current_user
from ingestion.documents import list_documents


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/sidebar")
async def get_workspace_sidebar(
    conversation_limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "documents": list_documents(current_user.user_id),
        "conversations": list_conversations(
            current_user.user_id,
            limit=conversation_limit,
        ),
    }
