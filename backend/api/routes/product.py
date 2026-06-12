import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.conversations import (
    delete_conversation,
    get_conversation,
    list_conversations,
)
from agent.graph import ask_agent, stream_agent_events
from api.routes.ingest import enqueue_ingestion_upload
from core.auth import CurrentUser, get_current_user
from ingestion.documents import (
    delete_document_record,
    get_document_by_id,
    list_documents,
)
from ingestion.file_storage import delete_upload
from ingestion.jobs import delete_job, get_job, list_jobs
from ingestion.task_queue import enqueue_ingestion_task
from ingestion.vector_store import delete_document_chunks


router = APIRouter(tags=["product"])


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    question: str
    document_ids: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=20)


def _format_sse(event: dict) -> str:
    event_type = event.get("type", "message")
    payload = json.dumps(event, ensure_ascii=True, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await enqueue_ingestion_upload(file, replace, current_user)


@router.get("/documents")
async def get_documents(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "documents": list_documents(current_user.user_id),
    }


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    record = get_document_by_id(current_user.user_id, document_id)

    if not record:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_document_chunks(document_id, user_id=current_user.user_id)
    delete_document_record(current_user.user_id, document_id)

    return {
        "document_id": document_id,
        "filename": record.filename,
        "deleted": True,
    }


@router.get("/jobs")
async def get_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "jobs": list_jobs(current_user.user_id, limit=limit),
    }


@router.get("/jobs/{job_id}")
async def get_product_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    job = get_job(job_id, user_id=current_user.user_id)

    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return job


@router.delete("/jobs/{job_id}")
async def delete_product_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    job = get_job(job_id, user_id=current_user.user_id)

    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    if job.status not in {"failed", "completed"}:
        raise HTTPException(
            status_code=409,
            detail="Only failed, stale, or completed ingestion jobs can be removed.",
        )

    cleanup_warning = None
    if job.upload_ref:
        try:
            delete_upload(job.upload_ref)
        except Exception as exc:
            cleanup_warning = str(exc)

    deleted = delete_job(job_id, current_user.user_id)
    return {
        "job_id": job_id,
        "deleted": deleted,
        "upload_cleanup_warning": cleanup_warning,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    job = get_job(job_id, user_id=current_user.user_id)

    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    if job.status not in {"failed"}:
        raise HTTPException(
            status_code=409,
            detail="Only failed or stale ingestion jobs can be retried.",
        )

    if not job.upload_ref:
        raise HTTPException(
            status_code=409,
            detail=(
                "This job cannot be retried because its original upload reference "
                "is missing. Please upload the document again."
            ),
        )

    from ingestion.jobs import update_job

    updated_job = update_job(
        job.job_id,
        current_user.user_id,
        status="queued",
        stage="queued",
        embedded_chunks=0,
        stored_chunks=0,
        error=None,
    )
    queue_task = enqueue_ingestion_task(
        {
            "job_id": updated_job.job_id,
            "upload_ref": updated_job.upload_ref,
            "filename": updated_job.filename,
            "user_id": current_user.user_id,
            "replaced_document_id": updated_job.replaced_document_id,
        }
    )

    return {
        "job": updated_job,
        "queue_task": queue_task,
    }


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return ask_agent(
        question=request.question,
        document_ids=request.document_ids,
        limit=request.limit,
        conversation_id=request.conversation_id,
        user_id=current_user.user_id,
    )


@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
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


@router.get("/conversations")
async def get_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "conversations": list_conversations(current_user.user_id, limit=limit),
    }


@router.get("/conversations/{conversation_id}")
async def get_product_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation = get_conversation(current_user.user_id, conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.delete("/conversations/{conversation_id}")
async def delete_product_conversation(
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
