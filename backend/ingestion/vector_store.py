import os
from typing import Callable
from uuid import uuid5, NAMESPACE_URL

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ingestion.models import DocumentChunk


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "legal_mind_chunks")
VECTOR_SIZE = 384
UPSERT_BATCH_SIZE = int(os.getenv("QDRANT_UPSERT_BATCH_SIZE", "64"))
QDRANT_UPSERT_WAIT = os.getenv("QDRANT_UPSERT_WAIT", "false").lower() == "true"


client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    timeout=300,
)


def ensure_collection() -> None:
    print(f"[qdrant] checking collection: {COLLECTION_NAME}", flush=True)
    existing_collections = client.get_collections().collections
    existing_names = [collection.name for collection in existing_collections]

    if COLLECTION_NAME in existing_names:
        print(f"[qdrant] collection exists: {COLLECTION_NAME}", flush=True)
        ensure_payload_indexes()
        return

    print(f"[qdrant] creating collection: {COLLECTION_NAME}", flush=True)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    ensure_payload_indexes()


def ensure_payload_indexes() -> None:
    try:
        collection_info = client.get_collection(COLLECTION_NAME)
        payload_schema = collection_info.payload_schema or {}

        for field_name in ["document_id", "user_id"]:
            if field_name in payload_schema:
                continue

            print(f"[qdrant] creating payload index: {field_name}", flush=True)
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
                timeout=300,
            )
    except Exception as exc:
        print(f"[qdrant] payload index check/create failed: {exc}", flush=True)
        raise


def store_chunks(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
    document_id: str | None = None,
    user_id: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    ensure_collection()

    points = []
    total = min(len(chunks), len(embeddings))
    print(f"[qdrant] preparing {total} points", flush=True)

    for point_index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{user_id or 'user'}:{document_id or 'document'}:{point_index}",
            )
        )
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "text": chunk.text,
                    "document_id": document_id,
                    "user_id": user_id,
                    **chunk.metadata,
                },
            )
        )

    total_batches = (len(points) + UPSERT_BATCH_SIZE - 1) // UPSERT_BATCH_SIZE
    print(
        f"[qdrant] upserting {len(points)} points in {total_batches} batches "
        f"of {UPSERT_BATCH_SIZE}, wait={QDRANT_UPSERT_WAIT}",
        flush=True,
    )

    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[start : start + UPSERT_BATCH_SIZE]
        batch_number = (start // UPSERT_BATCH_SIZE) + 1

        print(
            f"[qdrant] upsert batch {batch_number}/{total_batches} started "
            f"({len(batch)} points)",
            flush=True,
        )

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch,
            wait=QDRANT_UPSERT_WAIT,
            timeout=300,
        )
        processed_count = min(start + len(batch), len(points))

        if progress_callback:
            progress_callback(processed_count, len(points))

        print(
            f"[qdrant] upsert batch {batch_number}/{total_batches} completed",
            flush=True,
        )

    print(f"[qdrant] stored {len(points)} points", flush=True)
    return len(points)


def build_document_filter(
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> Filter | None:
    conditions = []

    if user_id:
        conditions.append(
            FieldCondition(
                key="user_id",
                match=MatchValue(value=user_id),
            )
        )

    if document_ids:
        conditions.append(
            FieldCondition(
                key="document_id",
                match=MatchAny(any=document_ids),
            )
        )

    if not conditions:
        return None

    return Filter(must=conditions)


def delete_document_chunks(document_id: str, user_id: str | None = None) -> None:
    ensure_collection()

    print(
        f"[qdrant] deleting chunks for document_id={document_id}, user_id={user_id}",
        flush=True,
    )
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=build_document_filter([document_id], user_id=user_id),
        wait=True,
        timeout=300,
    )
    print(f"[qdrant] deleted chunks for document_id={document_id}", flush=True)


def search_chunks(
    query_embedding: list[float],
    limit: int = 5,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> list[dict]:
    ensure_collection()
    query_filter = build_document_filter(document_ids, user_id=user_id)
    print(
        f"[qdrant] searching top {limit} chunks "
        f"user_id={user_id or 'all'}, document_ids={document_ids or 'all'}",
        flush=True,
    )

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "score": point.score,
            "text": point.payload.get("text", ""),
            "metadata": {
                key: value
                for key, value in point.payload.items()
                if key != "text"
            },
        }
        for point in response.points
    ]
