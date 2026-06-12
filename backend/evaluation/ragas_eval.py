import math
import os
import sys
import types
from typing import Any

from langchain_core.embeddings import Embeddings

from ingestion.embeddings import embed_texts


class MiniLMEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        return embed_texts([text])[0]


def _install_ragas_vertexai_shim() -> None:
    """RAGAS 0.4.x still imports an older Vertex AI LangChain path."""
    if "langchain_community.chat_models.vertexai" in sys.modules:
        return

    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError:
        return

    shim = types.ModuleType("langchain_community.chat_models.vertexai")
    shim.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = shim


def _clean_metric_value(value: Any) -> float | None:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(numeric_value):
        return None

    return round(numeric_value, 3)


def _build_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required to run RAGAS evaluation.")

    model_name = os.getenv("RAGAS_GEMINI_MODEL") or os.getenv("GEMINI_MODEL")
    if not model_name:
        raise RuntimeError("GEMINI_MODEL or RAGAS_GEMINI_MODEL is required.")

    return ChatGoogleGenerativeAI(
        model=model_name,
        api_key=api_key,
        temperature=0,
        timeout=int(os.getenv("RAGAS_LLM_TIMEOUT_SECONDS", "30")),
        max_retries=1,
    )


def _prepare_contexts(contexts: list[str]) -> list[str]:
    max_contexts = int(os.getenv("RAGAS_MAX_CONTEXTS", "2"))
    max_context_chars = int(os.getenv("RAGAS_MAX_CONTEXT_CHARS", "900"))

    prepared_contexts = []
    for context in contexts[:max_contexts]:
        cleaned_context = " ".join(context.split())
        if not cleaned_context:
            continue
        prepared_contexts.append(cleaned_context[:max_context_chars])

    return prepared_contexts


def evaluate_with_ragas(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
) -> dict[str, Any]:
    prepared_contexts = _prepare_contexts(contexts)

    if not prepared_contexts:
        raise ValueError("At least one retrieved context is required for RAGAS.")

    _install_ragas_vertexai_shim()

    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    metric_names_from_env = {
        metric_name.strip()
        for metric_name in os.getenv("RAGAS_METRICS", "faithfulness").split(",")
        if metric_name.strip()
    }
    metrics = [faithfulness]

    if "answer_relevancy" in metric_names_from_env:
        metrics.append(answer_relevancy)

    row: dict[str, Any] = {
        "user_input": question,
        "response": answer,
        "retrieved_contexts": prepared_contexts,
    }

    if ground_truth:
        row["reference"] = ground_truth
        if "context_precision" in metric_names_from_env:
            metrics.append(context_precision)
        if "context_recall" in metric_names_from_env:
            metrics.append(context_recall)

    result = evaluate(
        Dataset.from_list([row]),
        metrics=metrics,
        llm=_build_llm(),
        embeddings=MiniLMEmbeddings(),
        show_progress=False,
        raise_exceptions=False,
    )

    result_row = result.to_pandas().iloc[0].to_dict()
    metric_names = [metric.name for metric in metrics]
    metric_values = {
        metric_name: _clean_metric_value(result_row.get(metric_name))
        for metric_name in metric_names
    }

    available_scores = [
        score for score in metric_values.values() if isinstance(score, float)
    ]
    overall_score = (
        round(sum(available_scores) / len(available_scores), 3)
        if available_scores
        else None
    )

    return {
        "overall_score": overall_score,
        "metrics": metric_values,
        "context_count": len(prepared_contexts),
        "original_context_count": len(contexts),
        "max_context_chars": int(os.getenv("RAGAS_MAX_CONTEXT_CHARS", "900")),
        "metric_names": metric_names,
        "uses_ground_truth": bool(ground_truth),
        "notes": [
            "RAGAS uses an evaluator LLM, so it is slower and may cost API usage.",
            "Faithfulness checks whether the answer is supported by retrieved context.",
            "Set RAGAS_METRICS=faithfulness,answer_relevancy to run the slower relevancy metric.",
        ],
    }
