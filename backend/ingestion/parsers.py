import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import fitz
from bs4 import BeautifulSoup
from docx import Document

from ingestion.models import DocumentSection, ParsedDocument


def parse_txt(file_bytes: bytes, filename: str) -> ParsedDocument:
    text = file_bytes.decode("utf-8", errors="ignore")
    return ParsedDocument(
        title=filename,
        source_type="txt",
        sections=[DocumentSection(text=text, metadata={})],
    )


def parse_pdf(file_bytes: bytes, filename: str) -> ParsedDocument:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    sections = []

    for page_index, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            sections.append(
                DocumentSection(
                    text=text,
                    metadata={"page": page_index + 1},
                )
            )

    doc.close()

    return ParsedDocument(title=filename, source_type="pdf", sections=sections)


def parse_docx(file_bytes: bytes, filename: str) -> ParsedDocument:
    document = Document(BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]

    return ParsedDocument(
        title=filename,
        source_type="docx",
        sections=[
            DocumentSection(
                text="\n".join(paragraphs),
                metadata={"paragraph_count": len(paragraphs)},
            )
        ],
    )


def parse_csv(file_bytes: bytes, filename: str) -> ParsedDocument:
    text = file_bytes.decode("utf-8", errors="ignore")
    reader = csv.DictReader(StringIO(text))
    sections = []

    for row_index, row in enumerate(reader, start=1):
        row_text = ". ".join(f"{key}: {value}" for key, value in row.items())
        sections.append(
            DocumentSection(
                text=row_text,
                metadata={"row": row_index},
            )
        )

    return ParsedDocument(title=filename, source_type="csv", sections=sections)


def parse_json(file_bytes: bytes, filename: str) -> ParsedDocument:
    raw = file_bytes.decode("utf-8", errors="ignore")
    data = json.loads(raw)

    pretty_text = json.dumps(data, indent=2, ensure_ascii=False)

    return ParsedDocument(
        title=filename,
        source_type="json",
        sections=[DocumentSection(text=pretty_text, metadata={})],
    )


def parse_html(file_bytes: bytes, filename: str) -> ParsedDocument:
    html = file_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    clean_lines = [line.strip() for line in text.splitlines() if line.strip()]

    return ParsedDocument(
        title=filename,
        source_type="html",
        sections=[
            DocumentSection(
                text="\n".join(clean_lines),
                metadata={},
            )
        ],
    )


def parse_file(file_bytes: bytes, filename: str) -> ParsedDocument:
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(file_bytes, filename)
    if suffix == ".docx":
        return parse_docx(file_bytes, filename)
    if suffix == ".csv":
        return parse_csv(file_bytes, filename)
    if suffix == ".json":
        return parse_json(file_bytes, filename)
    if suffix in {".html", ".htm"}:
        return parse_html(file_bytes, filename)
    if suffix in {".txt", ".md"}:
        return parse_txt(file_bytes, filename)

    raise ValueError(f"Unsupported file type: {suffix}")