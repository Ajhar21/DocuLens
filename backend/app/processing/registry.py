from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from app.processing.base import DocumentParseError, ParsedDocument
from app.processing.image import parse_image
from app.processing.ocr import OcrEngine
from app.processing.pdf import parse_pdf
from app.processing.spreadsheet import parse_csv, parse_xlsx


def parse_document(
    file_path: Path,
    file_ext: Optional[str] = None,
    ocr_engine: Optional[OcrEngine] = None,
) -> ParsedDocument:
    ext = (file_ext or file_path.suffix).lower()

    if ext == ".pdf":
        return parse_pdf(file_path, ocr_engine=ocr_engine)
    if ext in {".png", ".jpg", ".jpeg"}:
        return parse_image(file_path, ocr_engine=ocr_engine)
    if ext == ".xlsx":
        return parse_xlsx(file_path)
    if ext == ".csv":
        return parse_csv(file_path)

    raise DocumentParseError(f"Unsupported file extension for parsing: {ext or '<none>'}")


PARSER_REGISTRY: dict[str, Callable[[Path], ParsedDocument]] = {
    ".pdf": parse_pdf,
    ".png": parse_image,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".xlsx": parse_xlsx,
    ".csv": parse_csv,
}
