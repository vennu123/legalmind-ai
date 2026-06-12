import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import google.auth
from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession


load_dotenv()

FIRESTORE_PROJECT_ID = (
    os.getenv("FIRESTORE_PROJECT_ID")
    or os.getenv("FIREBASE_PROJECT_ID")
    or os.getenv("GOOGLE_CLOUD_PROJECT")
)
FIRESTORE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
FIRESTORE_TIMEOUT_SECONDS = float(os.getenv("FIRESTORE_TIMEOUT_SECONDS", "10"))
FIRESTORE_API_BASE = "https://firestore.googleapis.com/v1"
FIRESTORE_SCOPES = ["https://www.googleapis.com/auth/datastore"]


@lru_cache(maxsize=1)
def get_firestore_session() -> AuthorizedSession:
    credentials, project_id = google.auth.default(scopes=FIRESTORE_SCOPES)
    if not FIRESTORE_PROJECT_ID and project_id:
        os.environ["FIRESTORE_PROJECT_ID"] = project_id
    return AuthorizedSession(credentials)


def _project_id() -> str:
    project_id = FIRESTORE_PROJECT_ID or os.getenv("FIRESTORE_PROJECT_ID")
    if not project_id:
        raise ValueError("FIRESTORE_PROJECT_ID must be set")
    return project_id


def _base_documents_url() -> str:
    return (
        f"{FIRESTORE_API_BASE}/projects/{_project_id()}"
        f"/databases/{FIRESTORE_DATABASE_ID}/documents"
    )


def _path_url(document_path: str) -> str:
    safe_path = "/".join(quote(part, safe="") for part in document_path.split("/") if part)
    return f"{_base_documents_url()}/{safe_path}"


def _collection_url(parent_path: str, collection_id: str) -> str:
    parent_url = _path_url(parent_path) if parent_path else _base_documents_url()
    return f"{parent_url}/{quote(collection_id, safe='')}"


def encode_firestore_value(value: Any) -> dict[str, Any]:
    if isinstance(value, datetime):
        return {"timestampValue": value.isoformat().replace("+00:00", "Z")}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if value is None:
        return {"nullValue": None}
    if isinstance(value, list):
        return {
            "arrayValue": {
                "values": [encode_firestore_value(item) for item in value],
            }
        }
    if isinstance(value, dict):
        return {
            "mapValue": {
                "fields": encode_firestore_fields(value),
            }
        }

    return {"stringValue": str(value)}


def encode_firestore_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {key: encode_firestore_value(value) for key, value in data.items()}


def decode_firestore_value(value: dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "timestampValue" in value:
        timestamp = value["timestampValue"].replace("Z", "+00:00")
        return datetime.fromisoformat(timestamp)
    if "nullValue" in value:
        return None
    if "arrayValue" in value:
        return [
            decode_firestore_value(item)
            for item in value.get("arrayValue", {}).get("values", [])
        ]
    if "mapValue" in value:
        return decode_firestore_fields(value.get("mapValue", {}).get("fields", {}))

    return None


def decode_firestore_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: decode_firestore_value(value) for key, value in fields.items()}


def get_document(document_path: str) -> dict[str, Any] | None:
    response = get_firestore_session().get(
        _path_url(document_path),
        timeout=FIRESTORE_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return decode_firestore_fields(response.json().get("fields", {}))


def set_document(document_path: str, data: dict[str, Any]) -> None:
    response = get_firestore_session().patch(
        _path_url(document_path),
        json={"fields": encode_firestore_fields(data)},
        timeout=FIRESTORE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def delete_document(document_path: str) -> bool:
    response = get_firestore_session().delete(
        _path_url(document_path),
        timeout=FIRESTORE_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


def list_collection(
    parent_path: str,
    collection_id: str,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    documents = []
    page_token = None

    while True:
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token

        response = get_firestore_session().get(
            _collection_url(parent_path, collection_id),
            params=params,
            timeout=FIRESTORE_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            return documents
        response.raise_for_status()

        payload = response.json()
        for document in payload.get("documents", []):
            decoded = decode_firestore_fields(document.get("fields", {}))
            decoded["__name__"] = document.get("name", "")
            decoded["__id__"] = document.get("name", "").rsplit("/", 1)[-1]
            documents.append(decoded)

        page_token = payload.get("nextPageToken")
        if not page_token:
            return documents


def ensure_user_document(user_id: str) -> None:
    set_document(
        f"users/{user_id}",
        {
            "user_id": user_id,
            "updated_at": datetime.now(timezone.utc),
        },
    )
