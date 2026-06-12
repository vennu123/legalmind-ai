from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.firestore import (
    delete_document as delete_firestore_document,
    ensure_user_document,
    get_document,
    list_collection,
    set_document,
)


class DocumentRecord(BaseModel):
    user_id: str = "local-dev-user"
    document_id: str
    filename: str
    source_type: str | None = None
    file_size_bytes: int
    chunk_count: int = 0
    stored_count: int = 0
    status: str = "processing"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def normalize_filename(filename: str) -> str:
    return Path(filename).name.strip().lower()


def _document_path(user_id: str, filename: str) -> str:
    return f"users/{user_id}/documents/{normalize_filename(filename)}"


def save_document(record: DocumentRecord) -> None:
    ensure_user_document(record.user_id)
    set_document(_document_path(record.user_id, record.filename), record.model_dump())


def get_document_by_filename(user_id: str, filename: str) -> DocumentRecord | None:
    data = get_document(_document_path(user_id, filename))

    if not data:
        return None

    return DocumentRecord(**data)


def list_documents(user_id: str) -> list[DocumentRecord]:
    records = [
        DocumentRecord(**data)
        for data in list_collection(f"users/{user_id}", "documents")
    ]

    return sorted(records, key=lambda record: record.updated_at, reverse=True)


def get_document_by_id(user_id: str, document_id: str) -> DocumentRecord | None:
    for record in list_documents(user_id):
        if record.document_id == document_id:
            return record

    return None


def delete_document_record(user_id: str, document_id: str) -> DocumentRecord | None:
    record = get_document_by_id(user_id, document_id)

    if not record:
        return None

    delete_firestore_document(_document_path(user_id, record.filename))
    return record


def upsert_document(user_id: str, filename: str, **updates: Any) -> DocumentRecord:
    existing = get_document_by_filename(user_id, filename)
    now = datetime.now(timezone.utc)

    data = existing.model_dump() if existing else {"user_id": user_id, "filename": filename}
    data["user_id"] = user_id
    data.update(updates)
    data["updated_at"] = now

    if not existing:
        data["created_at"] = now

    record = DocumentRecord(**data)
    save_document(record)
    return record
