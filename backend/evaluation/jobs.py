from datetime import datetime, timedelta, timezone
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from core.firestore import get_document, list_collection, set_document


STALE_EVAL_JOB_MINUTES = int(os.getenv("STALE_EVAL_JOB_MINUTES", "15"))


class EvaluationJob(BaseModel):
    job_id: str
    user_id: str
    status: str = "queued"
    stage: str = "queued"
    question: str
    answer: str
    contexts: list[str] = Field(default_factory=list)
    source_scores: list[float] = Field(default_factory=list)
    ground_truth: str | None = None
    result: dict[str, Any] | None = None
    fallback_result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _job_path(user_id: str, job_id: str) -> str:
    return f"users/{user_id}/evaluation_jobs/{job_id}"


def save_evaluation_job(job: EvaluationJob) -> None:
    set_document(_job_path(job.user_id, job.job_id), job.model_dump())


def create_evaluation_job(
    user_id: str,
    question: str,
    answer: str,
    contexts: list[str],
    source_scores: list[float] | None = None,
    ground_truth: str | None = None,
) -> EvaluationJob:
    job = EvaluationJob(
        job_id=str(uuid4()),
        user_id=user_id,
        question=question,
        answer=answer,
        contexts=contexts,
        source_scores=source_scores or [],
        ground_truth=ground_truth,
    )
    save_evaluation_job(job)
    return job


def get_evaluation_job(job_id: str, user_id: str) -> EvaluationJob | None:
    raw_job = get_document(_job_path(user_id, job_id))
    return mark_evaluation_job_stale_if_needed(EvaluationJob(**raw_job)) if raw_job else None


def list_evaluation_jobs(user_id: str, limit: int = 20) -> list[EvaluationJob]:
    jobs = [
        EvaluationJob(**data)
        for data in list_collection(f"users/{user_id}", "evaluation_jobs")
    ]
    jobs = [mark_evaluation_job_stale_if_needed(job) for job in jobs]
    return sorted(jobs, key=lambda job: job.updated_at, reverse=True)[:limit]


def update_evaluation_job(
    job_id: str,
    user_id: str,
    **updates: Any,
) -> EvaluationJob:
    job = get_evaluation_job(job_id, user_id)
    if not job:
        raise KeyError(f"Evaluation job not found: {job_id}")

    updated_job = EvaluationJob(
        **{
            **job.model_dump(),
            **updates,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    save_evaluation_job(updated_job)
    return updated_job


def mark_evaluation_job_stale_if_needed(job: EvaluationJob) -> EvaluationJob:
    if job.status not in {"queued", "processing"}:
        return job

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_EVAL_JOB_MINUTES)
    updated_at = job.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    if updated_at >= cutoff:
        return job

    stale_job = EvaluationJob(
        **{
            **job.model_dump(),
            "status": "failed",
            "stage": "stale",
            "error": (
                "Evaluation job became stale, likely because the backend stopped "
                "or reloaded while RAGAS was running. Please run Deep Eval again."
            ),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    save_evaluation_job(stale_job)
    return stale_job
