from agent_tools.check_compliance import check_compliance
from agent_tools.compare_documents import compare_documents
from agent_tools.extract_entities import extract_entities
from agent_tools.search_document import search_document
from agent_tools.summarize_section import summarize_section
from core.guardrails import analyze_context_guardrails
from ingestion.documents import get_document_by_id


def combine_context_text(contexts: list[dict], max_chars: int = 8000) -> str:
    parts = []
    total_length = 0

    for context in contexts:
        text = " ".join(str(context.get("text", "")).split())
        if not text:
            continue

        remaining = max_chars - total_length
        if remaining <= 0:
            break

        parts.append(text[:remaining])
        total_length += len(parts[-1])

    return "\n\n".join(parts)


def summarize_document(
    query: str = "Summarize this document",
    limit: int = 10,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    summary_queries = [
        query,
        "parties purpose agreement employment compensation obligations duties",
        "term termination notice cause resignation severance survival",
        "confidentiality intellectual property work product noncompete nonsolicit indemnification liability governing law dispute",
    ]
    contexts_by_key = {}

    for summary_query in summary_queries:
        for context in search_document(
            summary_query,
            limit,
            document_ids=document_ids,
            user_id=user_id,
        ):
            metadata = context.get("metadata", {})
            key = (
                metadata.get("document_id"),
                metadata.get("chunk_index"),
                context.get("text", "")[:120],
            )
            contexts_by_key[key] = context

    contexts = list(contexts_by_key.values())[: max(limit * 3, limit)]
    combined_text = combine_context_text(contexts)
    summary = summarize_section(combined_text)

    return {
        "query": query,
        "document_ids": document_ids or [],
        "retrieved_context_count": len(contexts),
        "guardrails": analyze_context_guardrails(contexts),
        "summary": summary,
        "retrieved_contexts": contexts,
    }


def extract_document_entities(
    query: str = "parties dates money obligations deadlines",
    limit: int = 10,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    contexts = search_document(query, limit, document_ids=document_ids, user_id=user_id)
    combined_text = combine_context_text(contexts)
    entities = extract_entities(combined_text)

    return {
        "query": query,
        "document_ids": document_ids or [],
        "retrieved_context_count": len(contexts),
        "guardrails": analyze_context_guardrails(contexts),
        "entities": entities,
        "retrieved_contexts": contexts,
    }


def check_document_compliance(
    query: str,
    clause_type: str = "general",
    limit: int = 10,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    contexts = search_document(query, limit, document_ids=document_ids, user_id=user_id)
    combined_text = combine_context_text(contexts)
    compliance = check_compliance(combined_text, clause_type)

    return {
        "query": query,
        "clause_type": clause_type,
        "document_ids": document_ids or [],
        "retrieved_context_count": len(contexts),
        "guardrails": analyze_context_guardrails(contexts),
        "compliance": compliance,
        "retrieved_contexts": contexts,
    }


def compare_selected_documents(
    query: str,
    document_ids: list[str],
    limit_per_document: int = 5,
    user_id: str | None = None,
) -> dict:
    document_contexts = []

    for document_id in document_ids:
        document_record = get_document_by_id(user_id, document_id) if user_id else None
        document_name = document_record.filename if document_record else document_id
        contexts = search_document(
            query,
            limit_per_document,
            document_ids=[document_id],
            user_id=user_id,
        )
        document_contexts.append(
            {
                "document_id": document_id,
                "document_name": document_name,
                "contexts": contexts,
                "combined_text": combine_context_text(contexts, max_chars=5000),
            }
        )

    if len(document_contexts) < 2:
        return {
            "query": query,
            "document_ids": document_ids,
            "summary": "At least two selected documents are needed for comparison.",
            "comparisons": [],
            "document_contexts": document_contexts,
            "guardrails": analyze_context_guardrails(
                [
                    context
                    for document_context in document_contexts
                    for context in document_context.get("contexts", [])
                ]
            ),
        }

    comparisons = []
    first_document = document_contexts[0]

    for other_document in document_contexts[1:]:
        comparisons.append(
            {
                "first_document_id": first_document["document_id"],
                "first_document_name": first_document["document_name"],
                "second_document_id": other_document["document_id"],
                "second_document_name": other_document["document_name"],
                "comparison": compare_documents(
                    first_document["combined_text"],
                    other_document["combined_text"],
                    query,
                    first_name=first_document["document_name"],
                    second_name=other_document["document_name"],
                ),
            }
        )

    return {
        "query": query,
        "document_ids": document_ids,
        "summary": "Compared selected documents using retrieved relevant chunks.",
        "comparisons": comparisons,
        "document_contexts": document_contexts,
        "guardrails": analyze_context_guardrails(
            [
                context
                for document_context in document_contexts
                for context in document_context.get("contexts", [])
            ]
        ),
    }
