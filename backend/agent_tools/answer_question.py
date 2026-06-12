from agent_tools.answer_from_context import answer_from_context
from agent_tools.search_document import search_document
from core.guardrails import analyze_context_guardrails


def answer_question(
    question: str,
    limit: int = 5,
    document_ids: list[str] | None = None,
    user_id: str | None = None,
) -> dict:
    contexts = search_document(question, limit, document_ids=document_ids, user_id=user_id)
    answer = answer_from_context(question, contexts)

    return {
        "question": question,
        "document_ids": document_ids or [],
        "answer": answer["answer"],
        "confidence": answer["confidence"],
        "citations": answer["citations"],
        "retrieved_context_count": len(contexts),
        "guardrails": analyze_context_guardrails(contexts),
        "retrieved_contexts": contexts,
    }
