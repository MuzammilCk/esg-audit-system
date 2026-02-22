from __future__ import annotations

from typing import Any, Dict, Literal
from uuid import UUID

from pydantic import BaseModel, Field


SourceType = Literal["s3", "local", "http", "gdrive"]


class IngestRequest(BaseModel):
    source_type: SourceType
    path: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestedDocument(BaseModel):
    document_id: UUID
    raw_bytes: str  # Base64-encoded
    metadata: Dict[str, Any]
    mime_type: str
    source_url: str


class NormalizedTable(BaseModel):
    page: int = Field(..., ge=1)
    data: list[list[str]]


class NormalizedImage(BaseModel):
    page: int = Field(..., ge=1)
    base64: str
    caption: str = ""


class NormalizedStructure(BaseModel):
    pages: int = Field(..., ge=1)
    sections: list[dict[str, Any]] = Field(default_factory=list)


class NormalizedDocument(BaseModel):
    document_id: UUID
    text_content: str
    tables: list[NormalizedTable] = Field(default_factory=list)
    images: list[NormalizedImage] = Field(default_factory=list)
    structure: NormalizedStructure
