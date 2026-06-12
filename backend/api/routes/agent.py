import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.conversations import (
    delete_conversation,
    get_conversation,
    list_conversations,
)
from agent.graph import ask_agent, stream_agent_events
from core.auth import CurrentUser, get_current_user


router = APIRouter(prefix="/agent", tags=["agent"])


class AgentAskRequest(BaseModel):
    conversation_id: str | None = None
    question: str
    document_ids: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=20)


@router.get("/conversations")
async def list_agent_conversations(
    limit: int = 50,
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "conversations": list_conversations(current_user.user_id, limit=limit),
    }


@router.get("/conversations/{conversation_id}")
async def get_agent_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation = get_conversation(current_user.user_id, conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.delete("/conversations/{conversation_id}")
async def delete_agent_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = delete_conversation(current_user.user_id, conversation_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "conversation_id": conversation_id,
        "deleted": True,
    }


@router.post("/ask")
async def ask_agent_route(
    request: AgentAskRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return ask_agent(
        question=request.question,
        document_ids=request.document_ids,
        limit=request.limit,
        conversation_id=request.conversation_id,
        user_id=current_user.user_id,
    )


def _format_sse(event: dict) -> str:
    event_type = event.get("type", "message")
    payload = json.dumps(event, ensure_ascii=True, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/stream")
async def stream_agent_route(
    request: AgentAskRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    def event_generator():
        for event in stream_agent_events(
            question=request.question,
            document_ids=request.document_ids,
            limit=request.limit,
            conversation_id=request.conversation_id,
            user_id=current_user.user_id,
        ):
            yield _format_sse(event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
