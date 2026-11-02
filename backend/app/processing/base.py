from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.parse import ParsedDocument, ParsedPage, ParsedTable


class DocumentParseError(Exception):
    """Raised when a document is corrupt, password-protected, or unreadable."""


class DocumentParser(Protocol):
    def __call__(self, file_path: Path) -> ParsedDocument:
        ...


__all__ = [
    "DocumentParseError",
    "DocumentParser",
    "ParsedDocument",
    "ParsedPage",
    "ParsedTable",
]
