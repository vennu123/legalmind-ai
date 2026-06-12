import os
import re
from pathlib import Path
from typing import Any


LEGAL_DISCLAIMER = (
    "Note: This is AI-generated document analysis for informational purposes only, "
    "not legal advice. Consult a qualified attorney before making legal decisions."
)

ALLOWED_UPLOAD_EXTENSIONS = {
    extension.strip().lower()
    for extension in os.getenv(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".pdf,.docx,.txt,.md,.json,.csv,.html,.htm",
    ).split(",")
    if extension.strip()
}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(40 * 1024 * 1024)))
WEAK_EVIDENCE_SCORE_THRESHOLD = float(os.getenv("WEAK_EVIDENCE_SCORE_THRESHOLD", "0.35"))

PROMPT_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
        r"system\s+prompt",
        r"developer\s+message",
        r"reveal\s+(the\s+)?(prompt|instructions|secrets)",
        r"you\s+are\s+now\s+.{0,40}(developer|system|admin)",
    ]
]

SENSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
        r"secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
        r"password\s*[:=]\s*['\"]?[^,\s]{8,}",
        r"-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----",
        r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}",
    ]
]

RISKY_LEGAL_PHRASES = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\byou should sign\b",
        r"\byou are legally safe\b",
        r"\bthis contract is enforceable\b",
        r"\bthis clause is enforceable\b",
        r"\bthis agreement is valid\b",
    ]
]


def validate_upload_file(filename: str, file_size_bytes: int) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{suffix}'. Allowed types: {allowed}.")

    if file_size_bytes > MAX_UPLOAD_BYTES:
        max_mb = round(MAX_UPLOAD_BYTES / (1024 * 1024), 1)
        raise ValueError(f"File is too large. Maximum allowed size is {max_mb} MB.")


def find_prompt_injection_flags(text: str) -> list[str]:
    return [
        pattern.pattern
        for pattern in PROMPT_INJECTION_PATTERNS
        if pattern.search(text)
    ]


def find_sensitive_data_flags(text: str) -> list[str]:
    return [pattern.pattern for pattern in SENSITIVE_PATTERNS if pattern.search(text)]


def is_assistant_secret_request(text: str) -> bool:
    lower_text = text.lower()
    blocked_phrases = [
        "system prompt",
        "developer message",
        "hidden instructions",
        "reveal your prompt",
        "show your prompt",
        "show me your instructions",
        "api key",
        "secret key",
    ]
    return any(phrase in lower_text for phrase in blocked_phrases)


def analyze_context_guardrails(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    joined_text = "\n".join(str(context.get("text", "")) for context in contexts)
    scores = [
        float(context["score"])
        for context in contexts
        if isinstance(context.get("score"), int | float)
    ]
    average_score = round(sum(scores) / len(scores), 3) if scores else None

    return {
        "prompt_injection_detected": bool(find_prompt_injection_flags(joined_text)),
        "sensitive_data_detected": bool(find_sensitive_data_flags(joined_text)),
        "weak_evidence": average_score is not None
        and average_score < WEAK_EVIDENCE_SCORE_THRESHOLD,
        "average_source_score": average_score,
        "context_count": len(contexts),
    }


def answer_not_found_message(selected_document_count: int = 0) -> str:
    scope = (
        "the selected documents"
        if selected_document_count
        else "the available documents"
    )
    return (
        f"I could not find enough support for this in {scope}. "
        "Try selecting a more relevant document or asking a narrower question."
    )


def sanitize_legal_language(answer: str) -> str:
    safe_answer = answer
    for pattern in RISKY_LEGAL_PHRASES:
        safe_answer = pattern.sub("this may require attorney review", safe_answer)
    return safe_answer


def append_guardrail_notes(
    answer: str,
    guardrail_report: dict[str, Any],
    include_disclaimer: bool = True,
) -> str:
    safe_answer = sanitize_legal_language(answer).strip()
    notes = []

    if guardrail_report.get("weak_evidence"):
        notes.append(
            "Evidence note: The retrieved document evidence appears weak, so this answer may be incomplete."
        )
    if guardrail_report.get("prompt_injection_detected"):
        notes.append(
            "Safety note: Potential prompt-injection text was detected in retrieved document content and treated only as document text."
        )
    if guardrail_report.get("sensitive_data_detected"):
        notes.append(
            "Sensitive data note: Retrieved content may contain secrets or sensitive identifiers; avoid sharing it unnecessarily."
        )
    if include_disclaimer:
        notes.append(LEGAL_DISCLAIMER)

    if not notes:
        return safe_answer

    return safe_answer + "\n\n" + "\n".join(notes)
