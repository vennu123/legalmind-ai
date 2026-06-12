import asyncio
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.auth import CurrentUser, get_current_user
from evaluation.jobs import create_evaluation_job, get_evaluation_job, list_evaluation_jobs
from evaluation.rag_eval import evaluate_rag
from evaluation.ragas_eval import evaluate_with_ragas
from evaluation.tasks import run_ragas_evaluation_job
from evaluation.task_queue import enqueue_ragas_evaluation_job


router = APIRouter(prefix="/eval", tags=["evaluation"])


class RagEvalRequest(BaseModel):
    question: str
    answer: str
    contexts: list[str] = Field(default_factory=list)
    source_scores: list[float] = Field(default_factory=list)
    ground_truth: str | None = None


class RagEvalTaskRequest(BaseModel):
    job_id: str
    user_id: str


@router.post("/rag")
async def evaluate_rag_answer(
    request: RagEvalRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "user_id": current_user.user_id,
        "evaluation": evaluate_rag(
            question=request.question,
            answer=request.answer,
            contexts=request.contexts,
            source_scores=request.source_scores,
            ground_truth=request.ground_truth,
        ),
    }


@router.post("/ragas")
async def evaluate_ragas_answer(
    request: RagEvalRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    timeout_seconds = int(os.getenv("RAGAS_EVAL_TIMEOUT_SECONDS", "180"))

    try:
        evaluation = await asyncio.wait_for(
            asyncio.to_thread(
                evaluate_with_ragas,
                question=request.question,
                answer=request.answer,
                contexts=request.contexts,
                ground_truth=request.ground_truth,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        fallback_evaluation = evaluate_rag(
            question=request.question,
            answer=request.answer,
            contexts=request.contexts,
            source_scores=request.source_scores,
            ground_truth=request.ground_truth,
        )
        return {
            "user_id": current_user.user_id,
            "evaluation": {
                "status": "timed_out",
                "overall_score": fallback_evaluation["overall_score"],
                "metrics": {
                    "quick_retrieval_coverage": fallback_evaluation[
                        "retrieval_coverage"
                    ],
                    "quick_answer_relevance": fallback_evaluation[
                        "answer_relevance"
                    ],
                    "quick_grounding_overlap": fallback_evaluation[
                        "grounding_overlap"
                    ],
                },
                "context_count": len(request.contexts),
                "metric_names": [],
                "uses_ground_truth": bool(request.ground_truth),
                "notes": [
                    (
                        f"RAGAS timed out after {timeout_seconds} seconds before "
                        "returning a score."
                    ),
                    "Showing the quick heuristic evaluation as a fallback.",
                    (
                        "For production, run RAGAS as a background evaluation job "
                        "instead of inside the chat request."
                    ),
                ],
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "user_id": current_user.user_id,
        "evaluation": evaluation,
    }


@router.post("/ragas/jobs")
async def create_ragas_evaluation_job(
    request: RagEvalRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not request.contexts:
        raise HTTPException(
            status_code=400,
            detail="At least one retrieved context is required for RAGAS.",
        )

    job = create_evaluation_job(
        user_id=current_user.user_id,
        question=request.question,
        answer=request.answer,
        contexts=request.contexts,
        source_scores=request.source_scores,
        ground_truth=request.ground_truth,
    )
    queue_task = enqueue_ragas_evaluation_job(job.job_id, current_user.user_id)

    return {
        "job": job,
        "queue_task": queue_task,
    }


@router.get("/ragas/jobs")
async def get_ragas_evaluation_jobs(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "jobs": list_evaluation_jobs(current_user.user_id),
    }


@router.get("/ragas/jobs/{job_id}")
async def get_ragas_evaluation_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    job = get_evaluation_job(job_id, current_user.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Evaluation job not found")

    return job


@router.post("/ragas/tasks/run")
async def run_ragas_evaluation_task_handler(
    request: RagEvalTaskRequest,
    x_evaluation_task_secret: str | None = Header(default=None),
):
    expected_secret = os.getenv("EVALUATION_TASK_SECRET")
    if expected_secret and x_evaluation_task_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid evaluation task secret")

    run_ragas_evaluation_job(job_id=request.job_id, user_id=request.user_id)
    return {
        "job_id": request.job_id,
        "status": "processed",
    }
