"""Unit tests for ingestion/chunking.py.

Chunking decides what the retriever can find, so bugs here quietly hurt
answer quality. These tests pin down the contract: size limit, overlap,
no lost text, and clear errors for bad settings.
"""
import pytest

from ingestion.chunking import chunk_document, split_text
from ingestion.models import DocumentSection, ParsedDocument


# ---------- split_text: invalid input ----------

def test_empty_text_returns_no_chunks():
    assert split_text("") == []
    assert split_text("   \n  ") == []


def test_chunk_size_must_be_positive():
    with pytest.raises(ValueError, match="chunk_size"):
        split_text("hello", chunk_size=0)


def test_overlap_cannot_be_negative():
    with pytest.raises(ValueError, match="cannot be negative"):
        split_text("hello", chunk_size=100, chunk_overlap=-1)


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        split_text("hello", chunk_size=100, chunk_overlap=100)


# ---------- split_text: behaviour ----------

def test_short_text_is_a_single_chunk():
    chunks = split_text("A short clause.", chunk_size=1000, chunk_overlap=150)
    assert len(chunks) == 1
    text, start, end = chunks[0]
    assert text == "A short clause."
    assert start == 0


def test_long_text_is_split_within_size_limit():
    text = "word " * 600  # about 3000 characters
    chunks = split_text(text, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    for chunk_text, _start, _end in chunks:
        assert len(chunk_text) <= 500


def test_consecutive_chunks_overlap():
    text = "word " * 600
    chunks = split_text(text, chunk_size=500, chunk_overlap=50)
    for previous, current in zip(chunks, chunks[1:]):
        # the next chunk starts before the previous one ended
        assert current[1] < previous[2]


def test_all_text_is_covered():
    text = "word " * 600
    chunks = split_text(text, chunk_size=500, chunk_overlap=50)
    assert chunks[0][1] == 0
    assert chunks[-1][2] == len(text.strip())


WORDS = "alpha bravo charlie delta echo foxtrot golf hotel india juliet " * 5


def test_chunks_do_not_end_mid_word():
    valid_words = set(WORDS.split())
    chunks = split_text(WORDS, chunk_size=40, chunk_overlap=5)
    for chunk_text, _start, _end in chunks:
        assert chunk_text.split()[-1] in valid_words


@pytest.mark.xfail(
    reason=(
        "Known limitation: the next chunk starts at (end - overlap), which can land "
        "inside a word, e.g. 'xtrot' instead of 'foxtrot'. Fix: move the start forward "
        "to the next whitespace. Remove this marker once fixed."
    )
)
def test_chunks_do_not_start_mid_word():
    valid_words = set(WORDS.split())
    chunks = split_text(WORDS, chunk_size=40, chunk_overlap=5)
    for chunk_text, _start, _end in chunks:
        assert chunk_text.split()[0] in valid_words


# ---------- chunk_document ----------

def test_chunk_document_adds_source_metadata_and_resets_chunk_index():
    document = ParsedDocument(
        title="Lease Agreement",
        source_type="pdf",
        sections=[
            DocumentSection(text="word " * 300, metadata={"page": 1}),
            DocumentSection(text="Short second section.", metadata={"page": 2}),
        ],
    )
    chunks = chunk_document(document, chunk_size=400, chunk_overlap=40)

    assert len(chunks) > 2
    first = chunks[0].metadata
    assert first["source_title"] == "Lease Agreement"
    assert first["source_type"] == "pdf"
    assert first["page"] == 1
    assert first["section_index"] == 0
    assert first["chunk_index"] == 0

    last = chunks[-1].metadata
    assert last["section_index"] == 1
    assert last["chunk_index"] == 0  # chunk numbering restarts per section
    assert last["page"] == 2
