from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.firestore import (
    delete_document,
    ensure_user_document,
    get_document,
    list_collection,
    set_document,
)


MAX_HISTORY_TURNS = 12


class ConversationTurn(BaseModel):
    question: str
    answer: str
    selected_tool: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationMetadata(BaseModel):
    user_id: str = "local-dev-user"
    conversation_id: str
    title: str
    document_ids: list[str] = Field(default_factory=list)
    turn_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def create_conversation_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_title(question: str) -> str:
    clean_question = " ".join(question.split())
    if not clean_question:
        return "New chat"
    return clean_question[:60]


def _conversation_path(user_id: str, conversation_id: str) -> str:
    return f"users/{user_id}/conversations/{conversation_id}"


def _turn_path(user_id: str, conversation_id: str, turn_id: str) -> str:
    return f"{_conversation_path(user_id, conversation_id)}/turns/{turn_id}"


def get_conversation_metadata(
    user_id: str,
    conversation_id: str,
) -> ConversationMetadata | None:
    data = get_document(_conversation_path(user_id, conversation_id))

    if not data:
        return None

    return ConversationMetadata(**data)


def save_conversation_metadata(metadata: ConversationMetadata) -> None:
    ensure_user_document(metadata.user_id)
    set_document(
        _conversation_path(metadata.user_id, metadata.conversation_id),
        metadata.model_dump(),
    )


def list_conversations(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    conversations = [
        ConversationMetadata(**data)
        for data in list_collection(f"users/{user_id}", "conversations")
    ]
    conversations = sorted(
        conversations,
        key=lambda conversation: conversation.updated_at,
        reverse=True,
    )

    return [
        conversation.model_dump(mode="json")
        for conversation in conversations[:limit]
    ]


def get_conversation_history(
    user_id: str,
    conversation_id: str | None,
) -> list[dict[str, Any]]:
    if not conversation_id:
        return []

    turns = [
        ConversationTurn(**data)
        for data in list_collection(
            _conversation_path(user_id, conversation_id),
            "turns",
        )
    ]
    turns = sorted(turns, key=lambda turn: turn.created_at, reverse=True)

    return [
        turn.model_dump(mode="json")
        for turn in reversed(turns[:MAX_HISTORY_TURNS])
    ]


def save_conversation_turn(
    user_id: str,
    conversation_id: str,
    question: str,
    answer: str,
    selected_tool: str | None,
    document_ids: list[str],
    confidence: str,
    sources: list[dict[str, Any]] | None = None,
) -> None:
    now = _utc_now()
    turn = ConversationTurn(
        question=question,
        answer=answer,
        selected_tool=selected_tool,
        document_ids=document_ids,
        confidence=confidence,
        sources=sources or [],
        created_at=now,
    )
    existing_metadata = get_conversation_metadata(user_id, conversation_id)
    metadata = ConversationMetadata(
        user_id=user_id,
        conversation_id=conversation_id,
        title=existing_metadata.title if existing_metadata else _build_title(question),
        document_ids=document_ids or (existing_metadata.document_ids if existing_metadata else []),
        turn_count=(existing_metadata.turn_count + 1) if existing_metadata else 1,
        created_at=existing_metadata.created_at if existing_metadata else now,
        updated_at=now,
    )

    set_document(
        _turn_path(user_id, conversation_id, str(now.timestamp())),
        turn.model_dump(),
    )
    save_conversation_metadata(metadata)


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    metadata = get_conversation_metadata(user_id, conversation_id)

    if not metadata:
        return None

    return {
        **metadata.model_dump(mode="json"),
        "turns": get_conversation_history(user_id, conversation_id),
    }


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    metadata = get_conversation_metadata(user_id, conversation_id)

    if not metadata:
        return False

    turns = list_collection(_conversation_path(user_id, conversation_id), "turns")
    for turn in turns:
        turn_id = turn.get("__id__")
        if turn_id:
            delete_document(_turn_path(user_id, conversation_id, turn_id))

    delete_document(_conversation_path(user_id, conversation_id))
    return True
