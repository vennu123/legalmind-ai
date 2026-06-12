import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.firestore import delete_document, get_document, list_collection, set_document


STALE_JOB_MINUTES = int(os.getenv("STALE_JOB_MINUTES", "30"))


class IngestionJob(BaseModel):
    job_id: str
    user_id: str = "local-dev-user"
    filename: str
    file_size_bytes: int
    document_id: str | None = None
    replaced_document_id: str | None = None
    upload_ref: str | None = None
    status: str = "queued"
    stage: str = "queued"
    total_chunks: int = 0
    embedded_chunks: int = 0
    stored_chunks: int = 0
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _job_path(user_id: str, job_id: str) -> str:
    return f"users/{user_id}/ingestion_jobs/{job_id}"


def save_job(job: IngestionJob) -> None:
    set_document(_job_path(job.user_id, job.job_id), job.model_dump())


def create_job(
    user_id: str,
    filename: str,
    file_size_bytes: int,
    document_id: str | None = None,
    replaced_document_id: str | None = None,
) -> IngestionJob:
    job = IngestionJob(
        job_id=str(uuid4()),
        user_id=user_id,
        filename=filename,
        file_size_bytes=file_size_bytes,
        document_id=document_id,
        replaced_document_id=replaced_document_id,
    )
    save_job(job)
    return job


def get_job(job_id: str, user_id: str | None = None) -> IngestionJob | None:
    if user_id:
        raw_job = get_document(_job_path(user_id, job_id))
        return mark_job_stale_if_needed(IngestionJob(**raw_job)) if raw_job else None

    # Fallback for worker code that only has job_id. This is less efficient but
    # keeps the task payload small and avoids duplicating job state.
    raise ValueError("user_id is required to fetch an ingestion job from Firestore")


def list_jobs(user_id: str, limit: int = 50) -> list[IngestionJob]:
    jobs = [
        IngestionJob(**data)
        for data in list_collection(f"users/{user_id}", "ingestion_jobs")
    ]
    jobs = [mark_job_stale_if_needed(job) for job in jobs]
    return sorted(jobs, key=lambda job: job.updated_at, reverse=True)[:limit]


def update_job(job_id: str, user_id: str, **updates: Any) -> IngestionJob:
    job = get_job(job_id, user_id=user_id)

    if not job:
        raise KeyError(f"Ingestion job not found: {job_id}")

    updated_data = {
        **job.model_dump(),
        **updates,
        "updated_at": datetime.now(timezone.utc),
    }
    updated_job = IngestionJob(**updated_data)
    save_job(updated_job)
    return updated_job


def delete_job(job_id: str, user_id: str) -> bool:
    return delete_document(_job_path(user_id, job_id))


def mark_job_stale_if_needed(job: IngestionJob) -> IngestionJob:
    if job.status not in {"queued", "processing"}:
        return job

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_JOB_MINUTES)
    updated_at = job.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    if updated_at >= cutoff:
        return job

    stale_job = IngestionJob(
        **{
            **job.model_dump(),
            "status": "failed",
            "stage": "stale",
            "error": (
                "Ingestion job became stale, likely because the backend stopped "
                "while processing. Please retry the job."
            ),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    save_job(stale_job)
    return stale_job
