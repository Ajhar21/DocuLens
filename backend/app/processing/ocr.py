from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from typing import Any, Optional

from app.processing.base import DocumentParseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: Optional[float] = None


class OcrEngine(ABC):
    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> OcrResult:
        raise NotImplementedError


class RapidOcrEngine(OcrEngine):
    def __init__(self) -> None:
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise DocumentParseError(
                    f"RapidOCR engine is not installed: {exc}"
                ) from exc
            self._engine = RapidOCR()
        return self._engine

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        if not image_bytes:
            raise DocumentParseError("Cannot run OCR on empty image bytes")

        engine = self._get_engine()
        try:
            result, _ = engine(image_bytes)
        except Exception as exc:
            raise DocumentParseError(f"OCR processing failed: {exc}") from exc

        if not result:
            return OcrResult(text="", confidence=None)

        lines: list[str] = []
        scores: list[float] = []
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text_piece = str(item[1]).strip()
            if text_piece:
                lines.append(text_piece)
            if len(item) >= 3 and item[2] is not None:
                try:
                    scores.append(float(item[2]))
                except (TypeError, ValueError):
                    pass

        avg_confidence: Optional[float] = None
        if scores:
            avg_confidence = round(sum(scores) / len(scores), 4)

        return OcrResult(text="\n".join(lines), confidence=avg_confidence)


_default_ocr_engine: Optional[RapidOcrEngine] = None


def get_ocr_engine() -> OcrEngine:
    global _default_ocr_engine
    if _default_ocr_engine is None:
        _default_ocr_engine = RapidOcrEngine()
    return _default_ocr_engine
