import re
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "shall",
    "that",
    "the",
    "this",
    "to",
    "you",
    "with",
}

BROAD_SUMMARY_TERMS = {
    "about",
    "clause",
    "clauses",
    "different",
    "document",
    "explain",
    "overview",
    "summarize",
    "summary",
    "what",
}

LEGAL_CLAUSE_TERMS = {
    "agreement",
    "assignment",
    "benefits",
    "breach",
    "compensation",
    "confidentiality",
    "damages",
    "effective",
    "employment",
    "expenses",
    "governing",
    "indemnity",
    "inventions",
    "liability",
    "non-compete",
    "noncompetition",
    "obligations",
    "parties",
    "payment",
    "purpose",
    "remedies",
    "restrictions",
    "salary",
    "term",
    "termination",
    "vesting",
}


def tokenize(text: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", text.lower())
    return {word for word in words if word not in STOPWORDS}


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def is_broad_summary_question(question_terms: set[str]) -> bool:
    return bool(question_terms & BROAD_SUMMARY_TERMS) and not bool(
        question_terms - BROAD_SUMMARY_TERMS
    )


def label_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def evaluate_rag(
    question: str,
    answer: str,
    contexts: list[str],
    source_scores: list[float] | None = None,
    ground_truth: str | None = None,
) -> dict[str, Any]:
    question_terms = tokenize(question)
    answer_terms = tokenize(answer)
    context_text = " ".join(contexts)
    context_terms = tokenize(context_text)
    ground_truth_terms = tokenize(ground_truth or "")

    source_scores = source_scores or []
    average_source_score = (
        round(sum(source_scores) / len(source_scores), 3)
        if source_scores
        else 0.0
    )

    retrieval_coverage = ratio(len(question_terms & context_terms), len(question_terms))
    answer_relevance = ratio(len(question_terms & answer_terms), len(question_terms))
    grounding_overlap = ratio(len(answer_terms & context_terms), len(answer_terms))
    covered_clause_terms = len(answer_terms & LEGAL_CLAUSE_TERMS)
    clause_coverage = ratio(
        min(covered_clause_terms, 6),
        min(6, len(LEGAL_CLAUSE_TERMS)),
    )
    ground_truth_overlap = (
        ratio(len(answer_terms & ground_truth_terms), len(ground_truth_terms))
        if ground_truth_terms
        else None
    )
    broad_summary_question = is_broad_summary_question(question_terms)

    notes = []
    if not contexts:
        notes.append("No retrieved contexts were provided.")
    if average_source_score and average_source_score < 0.35:
        notes.append("Average retrieval similarity is low; sources may be weak.")
    if grounding_overlap < 0.35:
        notes.append("The answer has low lexical overlap with the retrieved context.")
    if answer_relevance < 0.25 and not broad_summary_question:
        notes.append("The answer may not directly address the question terms.")
    if broad_summary_question:
        notes.append(
            "Broad summary questions are judged more by grounding and clause coverage than exact word overlap."
        )
    if ground_truth_overlap is not None and ground_truth_overlap < 0.35:
        notes.append("The answer has low overlap with the provided ground truth.")
    if not notes:
        notes.append("No obvious heuristic issues found.")

    if broad_summary_question:
        overall_score_parts = [
            grounding_overlap,
            clause_coverage,
            min(average_source_score, 1.0) if average_source_score else 0.0,
        ]
    else:
        overall_score_parts = [
            retrieval_coverage,
            answer_relevance,
            grounding_overlap,
            min(average_source_score, 1.0) if average_source_score else 0.0,
        ]
    if ground_truth_overlap is not None:
        overall_score_parts.append(ground_truth_overlap)

    overall_score = round(sum(overall_score_parts) / len(overall_score_parts), 3)

    return {
        "overall_score": overall_score,
        "overall_label": label_score(overall_score),
        "retrieval_coverage": retrieval_coverage,
        "answer_relevance": answer_relevance,
        "grounding_overlap": grounding_overlap,
        "clause_coverage": clause_coverage,
        "average_source_score": average_source_score,
        "ground_truth_overlap": ground_truth_overlap,
        "broad_summary_question": broad_summary_question,
        "context_count": len(contexts),
        "notes": notes,
    }
