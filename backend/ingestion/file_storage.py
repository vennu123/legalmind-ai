import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import storage


load_dotenv()

STORAGE_BACKEND = os.getenv("FILE_STORAGE_BACKEND", "local").lower()
LOCAL_UPLOAD_DIR = Path(os.getenv("INGESTION_UPLOAD_DIR", "storage/uploads"))
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GCS_UPLOAD_PREFIX = os.getenv("GCS_UPLOAD_PREFIX", "uploads")


def build_object_name(job_id: str, filename: str) -> str:
    safe_filename = Path(filename).name
    return f"{GCS_UPLOAD_PREFIX}/{job_id}_{safe_filename}"


def get_gcs_bucket():
    if not GCS_BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME must be set when FILE_STORAGE_BACKEND=gcs")

    client = storage.Client()
    return client.bucket(GCS_BUCKET_NAME)


def save_upload(job_id: str, filename: str, file_bytes: bytes) -> str:
    if STORAGE_BACKEND == "gcs":
        object_name = build_object_name(job_id, filename)
        blob = get_gcs_bucket().blob(object_name)
        blob.upload_from_string(file_bytes)
        return f"gcs://{GCS_BUCKET_NAME}/{object_name}"

    LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = LOCAL_UPLOAD_DIR / f"{job_id}_{Path(filename).name}"
    upload_path.write_bytes(file_bytes)
    return str(upload_path)


def read_upload(upload_ref: str) -> bytes:
    if upload_ref.startswith("gcs://"):
        bucket_name, object_name = upload_ref.removeprefix("gcs://").split("/", 1)
        blob = storage.Client().bucket(bucket_name).blob(object_name)
        return blob.download_as_bytes()

    return Path(upload_ref).read_bytes()


def delete_upload(upload_ref: str) -> None:
    if upload_ref.startswith("gcs://"):
        bucket_name, object_name = upload_ref.removeprefix("gcs://").split("/", 1)
        blob = storage.Client().bucket(bucket_name).blob(object_name)
        blob.delete()
        return

    path = Path(upload_ref)
    if path.exists():
        path.unlink()
