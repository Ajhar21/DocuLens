from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from app.processing.base import DocumentParseError, ParsedDocument, ParsedPage
from app.processing.ocr import OcrEngine, get_ocr_engine


def parse_image(
    file_path: Path,
    ocr_engine: Optional[OcrEngine] = None,
) -> ParsedDocument:
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise DocumentParseError("Image file is missing or empty")

    try:
        image_bytes = file_path.read_bytes()
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            img_format = (img.format or file_path.suffix.lstrip(".")).lower()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DocumentParseError(f"Corrupt or invalid image file: {exc}") from exc

    engine = ocr_engine or get_ocr_engine()
    ocr_res = engine.extract_text(image_bytes)

    return ParsedDocument(
        pages=[
            ParsedPage(
                page_number=1,
                text=ocr_res.text,
                source="ocr",
                ocr_confidence=ocr_res.confidence,
            )
        ],
        tables=[],
        metadata={
            "page_count": 1,
            "format": img_format,
            "width": width,
            "height": height,
        },
        ocr_used=True,
    )
