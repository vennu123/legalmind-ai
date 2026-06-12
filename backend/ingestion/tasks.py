from hashlib import sha256

from ingestion.chunking import chunk_document
from ingestion.documents import upsert_document
from ingestion.embeddings import embed_texts
from ingestion.file_storage import delete_upload, read_upload
from ingestion.jobs import get_job, update_job
from ingestion.parsers import parse_file
from ingestion.vector_store import delete_document_chunks, store_chunks


def run_ingestion_job(
    job_id: str,
    upload_ref: str,
    filename: str,
    user_id: str,
    replaced_document_id: str | None = None,
) -> None:
    completed = False
    try:
        update_job(job_id, user_id, status="processing", stage="reading_upload")
        file_bytes = read_upload(upload_ref)
        document_id = sha256(file_bytes).hexdigest()

        if replaced_document_id:
            update_job(job_id, user_id, stage="replacing_existing_document")
            delete_document_chunks(replaced_document_id, user_id=user_id)

        update_job(job_id, user_id, stage="parsing")
        print(f"[ingest/jobs] {job_id} parsing {filename}", flush=True)

        parsed = parse_file(file_bytes, filename)
        update_job(
            job_id,
            user_id,
            stage="chunking",
            result={
                "title": parsed.title,
                "source_type": parsed.source_type,
                "section_count": len(parsed.sections),
                "document_id": document_id,
            },
        )
        print(f"[ingest/jobs] {job_id} chunking document", flush=True)

        chunks = chunk_document(parsed)
        update_job(job_id, user_id, stage="embedding", total_chunks=len(chunks))
        print(f"[ingest/jobs] {job_id} created {len(chunks)} chunks", flush=True)

        def embedding_progress(processed: int, total: int) -> None:
            update_job(
                job_id,
                user_id,
                stage="embedding",
                embedded_chunks=processed,
                total_chunks=total,
            )

        embeddings = embed_texts(
            [chunk.text for chunk in chunks],
            progress_callback=embedding_progress,
        )

        update_job(
            job_id,
            user_id,
            stage="qdrant_upload",
            embedded_chunks=len(embeddings),
        )
        print(f"[ingest/jobs] {job_id} uploading to Qdrant", flush=True)

        def storage_progress(processed: int, total: int) -> None:
            update_job(
                job_id,
                user_id,
                stage="qdrant_upload",
                stored_chunks=processed,
                total_chunks=total,
            )

        stored_count = store_chunks(
            chunks,
            embeddings,
            document_id=document_id,
            user_id=user_id,
            progress_callback=storage_progress,
        )

        job = get_job(job_id, user_id=user_id)
        result = job.result if job and job.result else {}
        upsert_document(
            user_id,
            filename,
            document_id=document_id,
            source_type=parsed.source_type,
            file_size_bytes=len(file_bytes),
            chunk_count=len(chunks),
            stored_count=stored_count,
            status="ready",
        )
        update_job(
            job_id,
            user_id,
            status="completed",
            stage="completed",
            stored_chunks=stored_count,
            upload_ref=None,
            result={
                **result,
                "chunk_count": len(chunks),
                "stored_count": stored_count,
            },
        )
        completed = True
        print(f"[ingest/jobs] {job_id} completed", flush=True)

    except Exception as exc:
        update_job(
            job_id,
            user_id,
            status="failed",
            stage="failed",
            error=str(exc),
        )
        print(f"[ingest/jobs] {job_id} failed: {exc}", flush=True)

    finally:
        if completed:
            delete_upload(upload_ref)
