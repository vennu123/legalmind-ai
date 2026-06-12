from typing import Any
from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    title: str
    source_type: str
    sections: list[DocumentSection]


class DocumentChunk(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
