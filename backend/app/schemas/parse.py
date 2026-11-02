from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ParsedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int
    text: str
    source: Literal["text_layer", "ocr"]
    ocr_confidence: Optional[float] = None


class ParsedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[str]
    rows: list[list[Any]]


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[ParsedPage] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ocr_used: bool = False
