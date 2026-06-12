from ingestion.models import DocumentChunk, ParsedDocument


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[tuple[str, int, int]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    clean_text = text.strip()
    if not clean_text:
        return []

    chunks = []
    start = 0

    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))

        if end < len(clean_text):
            boundary = clean_text.rfind("\n", start, end)
            if boundary <= start:
                boundary = clean_text.rfind(" ", start, end)
            if boundary > start:
                end = boundary

        chunk_text = clean_text[start:end].strip()
        if chunk_text:
            chunks.append((chunk_text, start, end))

        if end >= len(clean_text):
            break
        next_start = max(end - chunk_overlap, 0)
        if next_start <= start:
           next_start = start + chunk_size
        start = next_start

    return chunks


def chunk_document(
    document: ParsedDocument,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    chunks = []

    for section_index, section in enumerate(document.sections):
        section_chunks = split_text(section.text, chunk_size, chunk_overlap)

        for chunk_index, (chunk_text, char_start, char_end) in enumerate(section_chunks):
            chunks.append(
                DocumentChunk(
                    text=chunk_text,
                    metadata={
                        **section.metadata,
                        "source_title": document.title,
                        "source_type": document.source_type,
                        "section_index": section_index,
                        "chunk_index": chunk_index,
                        "char_start": char_start,
                        "char_end": char_end,
                    },
                )
            )

    return chunks
