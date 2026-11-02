from __future__ import annotations

from pathlib import Path

import openpyxl
from PIL import Image, ImageDraw
import pymupdf as fitz
import pytest

from app.processing.base import DocumentParseError
from app.processing.image import parse_image
from app.processing.pdf import parse_pdf
from app.processing.spreadsheet import parse_csv, parse_xlsx


def test_parse_csv_utf8_sig_and_semicolon_delimiter(tmp_path: Path) -> None:
    csv_comma = tmp_path / "comma.csv"
    csv_comma.write_bytes("name,role,score\nAlice,admin,99\nBob,viewer,85\n".encode("utf-8-sig"))

    parsed_comma = parse_csv(csv_comma)
    assert parsed_comma.ocr_used is False
    assert len(parsed_comma.pages) == 1
    assert len(parsed_comma.tables) == 1
    assert parsed_comma.tables[0].columns == ["name", "role", "score"]
    assert parsed_comma.tables[0].rows == [["Alice", "admin", "99"], ["Bob", "viewer", "85"]]

    csv_semi = tmp_path / "semicolon.csv"
    csv_semi.write_text("item;qty;price\nWidget;4;19.99\nGadget;2;29.99\n", encoding="utf-8")

    parsed_semi = parse_csv(csv_semi)
    assert parsed_semi.metadata["delimiter"] == ";"
    assert parsed_semi.tables[0].columns == ["item", "qty", "price"]
    assert len(parsed_semi.tables[0].rows) == 2


def test_parse_xlsx_generated_with_blank_headers_and_empty_sheet(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "DataSheet"
    ws1.append(["Invoice", None, "Amount"])
    ws1.append(["INV-100", "Consulting", 1250.5])
    ws1.append(["INV-101", "Support", 300.0])

    wb.create_sheet(title="EmptySheet")
    wb.save(str(xlsx_path))
    wb.close()

    parsed = parse_xlsx(xlsx_path)
    assert parsed.ocr_used is False
    assert len(parsed.pages) == 2
    assert len(parsed.tables) == 2

    t1 = parsed.tables[0]
    assert t1.name == "DataSheet"
    assert t1.columns == ["Invoice", "column_2", "Amount"]
    assert len(t1.rows) == 2

    t2 = parsed.tables[1]
    assert t2.name == "EmptySheet"
    assert t2.columns == []
    assert t2.rows == []


def test_parse_text_layer_pdf_generated_in_test(tmp_path: Path) -> None:
    pdf_path = tmp_path / "text_doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "DocuLens automated test document with more than fifty characters in the PDF text layer so OCR is not triggered.",
    )
    doc.save(str(pdf_path))
    doc.close()

    parsed = parse_pdf(pdf_path)
    assert parsed.ocr_used is False
    assert len(parsed.pages) == 1
    assert parsed.pages[0].source == "text_layer"
    assert parsed.pages[0].ocr_confidence is None
    assert "DocuLens automated test document" in parsed.pages[0].text


def test_corrupt_files_produce_clean_error(tmp_path: Path) -> None:
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\ngarbage-not-a-valid-pdf-stream")

    with pytest.raises(DocumentParseError) as exc_info:
        parse_pdf(corrupt_pdf)
    assert "Traceback" not in str(exc_info.value)
    assert str(exc_info.value).strip() != ""

    corrupt_xlsx = tmp_path / "corrupt.xlsx"
    corrupt_xlsx.write_bytes(b"PK\x03\x04not-a-valid-zip-archive")

    with pytest.raises(DocumentParseError) as xlsx_exc:
        parse_xlsx(corrupt_xlsx)
    assert "Traceback" not in str(xlsx_exc.value)


def test_ocr_on_real_image(tmp_path: Path) -> None:
    pytest.importorskip("rapidocr_onnxruntime", reason="rapidocr-onnxruntime not installed")

    img_path = tmp_path / "hello_ocr.png"
    img = Image.new("RGB", (400, 120), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 45), "DOCULENS 2026", fill=(0, 0, 0))
    img.save(str(img_path), format="PNG")

    parsed = parse_image(img_path)
    assert parsed.ocr_used is True
    assert len(parsed.pages) == 1
    assert parsed.pages[0].source == "ocr"

    # Verify OCR text is actually readable, contains expected tokens, not just non-empty
    extracted = parsed.pages[0].text.upper()
    assert "DOCULENS" in extracted or "2026" in extracted
    if parsed.pages[0].ocr_confidence is not None:
        assert parsed.pages[0].ocr_confidence > 0.40


def test_password_protected_pdf_fails_fast(tmp_path: Path) -> None:
    enc_path = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Confidential Secret Payroll Data 2026")
    doc.save(
        str(enc_path),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="securepass123",
        owner_pw="adminpass123",
    )
    doc.close()

    with pytest.raises(DocumentParseError) as exc_info:
        parse_pdf(enc_path)
    assert "password-protected" in str(exc_info.value).lower()

