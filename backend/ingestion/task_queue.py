import json
import os
import threading
from base64 import b64encode
from typing import Any

import google.auth
from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession

from ingestion.tasks import run_ingestion_job


load_dotenv()

INGESTION_QUEUE_BACKEND = os.getenv("INGESTION_QUEUE_BACKEND", "local").lower()
CLOUD_TASKS_PROJECT_ID = os.getenv("CLOUD_TASKS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
CLOUD_TASKS_LOCATION = os.getenv("CLOUD_TASKS_LOCATION", "australia-southeast1")
CLOUD_TASKS_QUEUE_ID = os.getenv("CLOUD_TASKS_QUEUE_ID", "legalmind-ingestion")
INGESTION_TASK_HANDLER_URL = os.getenv("INGESTION_TASK_HANDLER_URL")
INGESTION_TASK_SECRET = os.getenv("INGESTION_TASK_SECRET")
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
        f"/queues/{CLOUD_TASKS_QUEUE_ID}"
    )


def _enqueue_cloud_task(payload: dict[str, Any]) -> dict[str, Any]:
    if not INGESTION_TASK_HANDLER_URL:
        raise ValueError("INGESTION_TASK_HANDLER_URL must be set for Cloud Tasks")

    headers = {"Content-Type": "application/json"}
    if INGESTION_TASK_SECRET:
        headers["X-Ingestion-Task-Secret"] = INGESTION_TASK_SECRET

    http_request: dict[str, Any] = {
        "httpMethod": "POST",
        "url": INGESTION_TASK_HANDLER_URL,
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


def _enqueue_local_thread(payload: dict[str, Any]) -> dict[str, Any]:
    thread = threading.Thread(
        target=run_ingestion_job,
        kwargs=payload,
        daemon=True,
    )
    thread.start()
    return {
        "backend": "local",
        "id": f"local-thread-{payload['job_id']}",
    }


def enqueue_ingestion_task(payload: dict[str, Any]) -> dict[str, Any]:
    if INGESTION_QUEUE_BACKEND == "cloud_tasks":
        return _enqueue_cloud_task(payload)

    return _enqueue_local_thread(payload)
