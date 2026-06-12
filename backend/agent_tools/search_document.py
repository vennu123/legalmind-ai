from ingestion.embeddings import embed_text
from ingestion.vector_store import search_chunks


def search_document(
    query: str,
    limit: int = 5,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> list[dict]:
    query_text = query.strip()

    if not query_text:
        return []

    query_embedding = embed_text(query_text)
    return search_chunks(
        query_embedding,
        limit,
        document_ids=document_ids,
        user_id=user_id,
    )
