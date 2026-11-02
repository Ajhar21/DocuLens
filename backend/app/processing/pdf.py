from __future__ import annotations

from pathlib import Path
from typing import Optional

import pymupdf as fitz

from app.core.config import settings
from app.processing.base import DocumentParseError, ParsedDocument, ParsedPage
from app.processing.ocr import OcrEngine, get_ocr_engine


def parse_pdf(
    file_path: Path,
    ocr_engine: Optional[OcrEngine] = None,
) -> ParsedDocument:
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise DocumentParseError("PDF file is missing or empty")

    try:
        doc = fitz.open(str(file_path))
    except Exception as exc:
        raise DocumentParseError(f"Corrupt or unreadable PDF file: {exc}") from exc

    try:
        if doc.needs_pass or doc.is_encrypted:
            raise DocumentParseError("PDF file is password-protected or encrypted")

        if doc.page_count == 0:
            raise DocumentParseError("PDF file contains 0 pages")

        pages: list[ParsedPage] = []
        ocr_used = False
        min_chars = settings.PDF_MIN_TEXT_CHARS
        dpi = settings.OCR_DPI

        for page_idx in range(doc.page_count):
            page_num = page_idx + 1
            try:
                page = doc.load_page(page_idx)
                raw_text = page.get_text("text") or ""
            except Exception as exc:
                raise DocumentParseError(
                    f"Failed to read page {page_num} of PDF: {exc}"
                ) from exc

            if len(raw_text.strip()) >= min_chars:
                pages.append(
                    ParsedPage(
                        page_number=page_num,
                        text=raw_text.strip(),
                        source="text_layer",
                        ocr_confidence=None,
                    )
                )
            else:
                engine = ocr_engine or get_ocr_engine()
                try:
                    pix = page.get_pixmap(dpi=dpi)
                    png_bytes = pix.tobytes("png")
                except Exception as exc:
                    raise DocumentParseError(
                        f"Failed to rasterize PDF page {page_num} for OCR: {exc}"
                    ) from exc

                ocr_res = engine.extract_text(png_bytes)
                ocr_used = True
                pages.append(
                    ParsedPage(
                        page_number=page_num,
                        text=ocr_res.text,
                        source="ocr",
                        ocr_confidence=ocr_res.confidence,
                    )
                )

        return ParsedDocument(
            pages=pages,
            tables=[],
            metadata={"page_count": len(pages), "format": "pdf"},
            ocr_used=ocr_used,
        )
    finally:
        doc.close()
