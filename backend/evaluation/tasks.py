import os
import signal
from contextlib import contextmanager

from evaluation.jobs import get_evaluation_job, update_evaluation_job
from evaluation.rag_eval import evaluate_rag
from evaluation.ragas_eval import evaluate_with_ragas


class EvaluationTimeoutError(TimeoutError):
    pass


@contextmanager
def evaluation_timeout(seconds: int):
    def handle_timeout(_signum, _frame):
        raise EvaluationTimeoutError(
            f"Deep Eval timed out after {seconds} seconds."
        )

    previous_handler = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def run_ragas_evaluation_job(job_id: str, user_id: str) -> None:
    print(f"[ragas/eval] loading job job_id={job_id}", flush=True)
    job = get_evaluation_job(job_id, user_id)
    if not job:
        print(f"[ragas/eval] job not found job_id={job_id}", flush=True)
        return

    print(f"[ragas/eval] marking processing job_id={job_id}", flush=True)
    update_evaluation_job(
        job_id,
        user_id,
        status="processing",
        stage="running_ragas",
        error=None,
    )

    print(f"[ragas/eval] computing quick fallback job_id={job_id}", flush=True)
    fallback_result = evaluate_rag(
        question=job.question,
        answer=job.answer,
        contexts=job.contexts,
        source_scores=job.source_scores,
        ground_truth=job.ground_truth,
    )

    try:
        timeout_seconds = int(os.getenv("RAGAS_WORKER_TIMEOUT_SECONDS", "240"))
        print(f"[ragas/eval] running ragas job_id={job_id}", flush=True)
        with evaluation_timeout(timeout_seconds):
            result = evaluate_with_ragas(
                question=job.question,
                answer=job.answer,
                contexts=job.contexts,
                ground_truth=job.ground_truth,
            )
        print(f"[ragas/eval] ragas completed job_id={job_id}", flush=True)
        update_evaluation_job(
            job_id,
            user_id,
            status="completed",
            stage="completed",
            result={**result, "status": "completed"},
            fallback_result=fallback_result,
            error=None,
        )
    except Exception as exc:
        print(f"[ragas/eval] ragas failed job_id={job_id}: {exc}", flush=True)
        update_evaluation_job(
            job_id,
            user_id,
            status="failed",
            stage="failed",
            result=None,
            fallback_result=fallback_result,
            error=str(exc),
        )
