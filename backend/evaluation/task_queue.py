import json
import os
import subprocess
import sys
from base64 import b64encode

import google.auth
from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession

from evaluation.jobs import update_evaluation_job


load_dotenv()

EVALUATION_QUEUE_BACKEND = os.getenv("EVALUATION_QUEUE_BACKEND", "local_process").lower()
CLOUD_TASKS_PROJECT_ID = os.getenv("CLOUD_TASKS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
CLOUD_TASKS_LOCATION = os.getenv("CLOUD_TASKS_LOCATION", "australia-southeast1")
EVALUATION_CLOUD_TASKS_QUEUE_ID = os.getenv(
    "EVALUATION_CLOUD_TASKS_QUEUE_ID",
    "legalmind-evaluation",
)
EVALUATION_TASK_HANDLER_URL = os.getenv("EVALUATION_TASK_HANDLER_URL")
EVALUATION_TASK_SECRET = os.getenv("EVALUATION_TASK_SECRET")
CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL = os.getenv("CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL")
CLOUD_TASKS_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _cloud_tasks_session() -> AuthorizedSession:
    credentials, _ = google.auth.default(scopes=CLOUD_TASKS_SCOPES)
    return AuthorizedSession(credentials)


def _cloud_tasks_parent() -> str:
    if not CLOUD_TASKS_PROJECT_ID:
        raise ValueError("CLOUD_TASKS_PROJECT_ID or GOOGLE_CLOUD_PROJECT must be set")
    return (
        f"projects/{CLOUD_TASKS_PROJECT_ID}/locations/{CLOUD_TASKS_LOCATION}"
        f"/queues/{EVALUATION_CLOUD_TASKS_QUEUE_ID}"
    )


def _enqueue_cloud_task(job_id: str, user_id: str) -> dict[str, str | None]:
    if not EVALUATION_TASK_HANDLER_URL:
        raise ValueError("EVALUATION_TASK_HANDLER_URL must be set for Cloud Tasks")

    headers = {"Content-Type": "application/json"}
    if EVALUATION_TASK_SECRET:
        headers["X-Evaluation-Task-Secret"] = EVALUATION_TASK_SECRET

    payload = {"job_id": job_id, "user_id": user_id}
    http_request = {
        "httpMethod": "POST",
        "url": EVALUATION_TASK_HANDLER_URL,
        "headers": headers,
        "body": b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"),
    }

    if CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL:
        http_request["oidcToken"] = {
            "serviceAccountEmail": CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL,
        }

    response = _cloud_tasks_session().post(
        f"https://cloudtasks.googleapis.com/v2/{_cloud_tasks_parent()}/tasks",
        json={"task": {"httpRequest": http_request}},
        timeout=20,
    )
    response.raise_for_status()
    task = response.json()
    return {
        "backend": "cloud_tasks",
        "id": task.get("name"),
    }


def _enqueue_local_process(job_id: str, user_id: str) -> dict[str, str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "evaluation.worker",
            "--job-id",
            job_id,
            "--user-id",
            user_id,
        ],
        cwd=".",
        start_new_session=True,
    )
    print(
        f"[ragas/eval] queued local process job_id={job_id} pid={process.pid}",
        flush=True,
    )
    return {
        "backend": "local_process",
        "id": f"local-ragas-eval-{job_id}",
        "pid": str(process.pid),
    }


def enqueue_ragas_evaluation_job(job_id: str, user_id: str) -> dict[str, str | None]:
    update_evaluation_job(
        job_id,
        user_id,
        status="processing",
        stage="starting_worker",
        error=None,
    )

    if EVALUATION_QUEUE_BACKEND == "cloud_tasks":
        return _enqueue_cloud_task(job_id, user_id)

    return _enqueue_local_process(job_id, user_id)
