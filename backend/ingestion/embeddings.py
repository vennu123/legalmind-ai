import os
from functools import lru_cache
from math import ceil
from typing import Callable

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


load_dotenv()

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    print(f"[embeddings] loading model: {EMBEDDING_MODEL_NAME}", flush=True)
    return SentenceTransformer(
        EMBEDDING_MODEL_NAME,
        local_files_only=True,
    )


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    embedding = model.encode(text)

    return embedding.tolist()


def embed_texts(
    texts: list[str],
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    model = get_embedding_model()
    all_embeddings = []
    total_batches = ceil(len(texts) / EMBEDDING_BATCH_SIZE) if texts else 0

    print(
        f"[embeddings] embedding {len(texts)} texts in {total_batches} batches",
        flush=True,
    )

    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[start : start + EMBEDDING_BATCH_SIZE]
        batch_number = (start // EMBEDDING_BATCH_SIZE) + 1

        print(
            f"[embeddings] batch {batch_number}/{total_batches} started",
            flush=True,
        )

        embeddings = model.encode(batch)
        all_embeddings.extend(embeddings.tolist())
        processed_count = min(start + len(batch), len(texts))

        if progress_callback:
            progress_callback(processed_count, len(texts))

        print(
            f"[embeddings] batch {batch_number}/{total_batches} completed",
            flush=True,
        )

    return all_embeddings
