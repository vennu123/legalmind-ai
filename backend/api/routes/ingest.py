from hashlib import sha256

import os

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from agent_tools.search_document import search_document
from core.auth import CurrentUser, get_current_user
from core.guardrails import validate_upload_file
from ingestion.chunking import chunk_document
from ingestion.documents import get_document_by_filename, list_documents
from ingestion.embeddings import embed_texts
from ingestion.file_storage import delete_upload, save_upload
from ingestion.jobs import create_job, get_job, update_job
from ingestion.parsers import parse_file
from ingestion.tasks import run_ingestion_job
from ingestion.task_queue import enqueue_ingestion_task
from ingestion.vector_store import store_chunks


router = APIRouter(prefix="/ingest", tags=["ingestion"])
INGESTION_TASK_SECRET = os.getenv("INGESTION_TASK_SECRET")


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    document_ids: list[str] | None = None


class IngestionTaskRequest(BaseModel):
    job_id: str
    upload_ref: str
    filename: str
    user_id: str
    replaced_document_id: str | None = None


@router.post("/preview")
async def preview_ingestion(file: UploadFile = File(...)):
    file_bytes = await file.read()
    parsed = parse_file(file_bytes, file.filename or "uploaded_file")

    return {
        "title": parsed.title,
        "source_type": parsed.source_type,
        "section_count": len(parsed.sections),
        "first_section_preview": parsed.sections[0].text[:500] if parsed.sections else "",
        "first_section_metadata": parsed.sections[0].metadata if parsed.sections else {},
    }


@router.post("/chunks/preview")
async def preview_chunks(file: UploadFile = File(...)):
    file_bytes = await file.read()
    parsed = parse_file(file_bytes, file.filename or "uploaded_file")
    chunks = chunk_document(parsed)

    return {
        "title": parsed.title,
        "source_type": parsed.source_type,
        "section_count": len(parsed.sections),
        "chunk_count": len(chunks),
        "first_chunk_preview": chunks[0].text[:500] if chunks else "",
        "first_chunk_metadata": chunks[0].metadata if chunks else {},
    }


@router.post("/embeddings/preview")
async def preview_embeddings(file: UploadFile = File(...)):
    file_bytes = await file.read()
    parsed = parse_file(file_bytes, file.filename or "uploaded_file")
    chunks = chunk_document(parsed)

    preview_chunks = chunks[:3]
    embeddings = embed_texts([chunk.text for chunk in preview_chunks])

    return {
        "title": parsed.title,
        "source_type": parsed.source_type,
        "section_count": len(parsed.sections),
        "chunk_count": len(chunks),
        "embedded_chunk_count": len(embeddings),
        "embedding_dimension": len(embeddings[0]) if embeddings else 0,
        "first_embedding_preview": embeddings[0][:5] if embeddings else [],
        "first_chunk_preview": preview_chunks[0].text[:300] if preview_chunks else "",
        "first_chunk_metadata": preview_chunks[0].metadata if preview_chunks else {},
    }


@router.post("/store")
async def store_ingestion(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    filename = file.filename or "uploaded_file"
    print(f"[ingest/store] reading upload: {filename}", flush=True)
    file_bytes = await file.read()
    document_id = sha256(file_bytes).hexdigest()
    print(f"[ingest/store] read {len(file_bytes)} bytes", flush=True)

    print("[ingest/store] parsing file", flush=True)
    parsed = parse_file(file_bytes, filename)
    print(
        f"[ingest/store] parsed source_type={parsed.source_type}, "
        f"sections={len(parsed.sections)}",
        flush=True,
    )

    print("[ingest/store] chunking document", flush=True)
    chunks = chunk_document(parsed)
    print(f"[ingest/store] created {len(chunks)} chunks", flush=True)

    print("[ingest/store] embedding chunks", flush=True)
    embeddings = embed_texts([chunk.text for chunk in chunks])
    print(f"[ingest/store] created {len(embeddings)} embeddings", flush=True)

    print("[ingest/store] storing chunks in Qdrant", flush=True)
    stored_count = store_chunks(
        chunks,
        embeddings,
        document_id=document_id,
        user_id=current_user.user_id,
    )
    print(f"[ingest/store] stored {stored_count} chunks", flush=True)

    return {
        "title": parsed.title,
        "source_type": parsed.source_type,
        "section_count": len(parsed.sections),
        "document_id": document_id,
        "chunk_count": len(chunks),
        "stored_count": stored_count,
    }


@router.post("/jobs")
async def create_ingestion_job(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await enqueue_ingestion_upload(file, replace, current_user)


async def enqueue_ingestion_upload(
    file: UploadFile,
    replace: bool,
    current_user: CurrentUser,
):
    filename = file.filename or "uploaded_file"
    validate_upload_file(filename, 0)
    print(
        f"[ingest/jobs] request received user_id={current_user.user_id} filename={filename}",
        flush=True,
    )
    file_bytes = await file.read()
    try:
        validate_upload_file(filename, len(file_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = sha256(file_bytes).hexdigest()
    print(
        f"[ingest/jobs] read upload bytes={len(file_bytes)} document_id={document_id}",
        flush=True,
    )

    try:
        print("[ingest/jobs] checking Firestore duplicate document metadata", flush=True)
        existing_document = get_document_by_filename(current_user.user_id, filename)
        print("[ingest/jobs] Firestore duplicate check completed", flush=True)
    except Exception as exc:
        print(f"[ingest/jobs] Firestore duplicate check failed: {exc}", flush=True)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to check document metadata in Firestore: {exc}",
        ) from exc

    replaced_document_id = None

    if existing_document and existing_document.document_id == document_id:
        return {
            "status": "already_exists",
            "message": "This exact file has already been uploaded. No new ingestion job was created.",
            "document": existing_document,
        }

    if existing_document and existing_document.document_id != document_id:
        if not replace:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "A file with this name already exists but the content is different. "
                        "Submit again with replace=true to replace the existing document."
                    ),
                    "existing_document_id": existing_document.document_id,
                    "new_document_id": document_id,
                    "filename": filename,
                },
            )

        replaced_document_id = existing_document.document_id

    job = create_job(
        user_id=current_user.user_id,
        filename=filename,
        file_size_bytes=len(file_bytes),
        document_id=document_id,
        replaced_document_id=replaced_document_id,
    )
    print(f"[ingest/jobs] created Firestore job status job_id={job.job_id}", flush=True)

    try:
        print("[ingest/jobs] saving upload to storage", flush=True)
        upload_ref = save_upload(job.job_id, filename, file_bytes)
        job = update_job(job.job_id, current_user.user_id, upload_ref=upload_ref)
        print(f"[ingest/jobs] saved upload upload_ref={upload_ref}", flush=True)
    except Exception as exc:
        update_job(
            job.job_id,
            current_user.user_id,
            status="failed",
            stage="upload_storage_failed",
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc

    try:
        print("[ingest/jobs] enqueueing ingestion task", flush=True)
        queue_task = enqueue_ingestion_task(
            {
                "job_id": job.job_id,
                "upload_ref": upload_ref,
                "filename": filename,
                "user_id": current_user.user_id,
                "replaced_document_id": replaced_document_id,
            }
        )
        print(f"[ingest/jobs] enqueued task={queue_task}", flush=True)
    except Exception as exc:
        delete_upload(upload_ref)
        update_job(
            job.job_id,
            current_user.user_id,
            status="failed",
            stage="enqueue_failed",
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Failed to enqueue ingestion job: {exc}",
        ) from exc

    return {
        "job_id": job.job_id,
        "queue_task": queue_task,
        "status": job.status,
        "stage": job.stage,
        "filename": job.filename,
        "file_size_bytes": job.file_size_bytes,
        "document_id": job.document_id,
        "replaced_document_id": job.replaced_document_id,
    }


@router.get("/documents")
async def list_ingested_documents(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "documents": list_documents(current_user.user_id),
    }


@router.get("/jobs/{job_id}")
async def get_ingestion_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    job = get_job(job_id, user_id=current_user.user_id)

    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return job


@router.post("/tasks/run")
async def run_ingestion_task_handler(
    request: IngestionTaskRequest,
    x_ingestion_task_secret: str | None = Header(default=None),
):
    if INGESTION_TASK_SECRET and x_ingestion_task_secret != INGESTION_TASK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid ingestion task secret")

    run_ingestion_job(
        job_id=request.job_id,
        upload_ref=request.upload_ref,
        filename=request.filename,
        user_id=request.user_id,
        replaced_document_id=request.replaced_document_id,
    )
    return {
        "job_id": request.job_id,
        "status": "processed",
    }


@router.post("/search")
async def search_ingestion(
    request: SearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    results = search_document(
        request.query,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )

    return {
        "query": request.query,
        "document_ids": request.document_ids or [],
        "result_count": len(results),
        "results": results,
    }
