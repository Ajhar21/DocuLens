from __future__ import annotations

import csv
from datetime import date, datetime, time
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any
import zipfile

import openpyxl

from app.core.config import settings
from app.processing.base import (
    DocumentParseError,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


def _serialize_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _normalize_header(raw_header: list[Any], num_cols: int) -> list[str]:
    columns: list[str] = []
    for idx in range(num_cols):
        val = raw_header[idx] if idx < len(raw_header) else None
        text = str(val).strip() if val is not None else ""
        if not text:
            text = f"column_{idx + 1}"
        columns.append(text)
    return columns


def _build_sheet_artifacts(
    sheet_name: str,
    page_number: int,
    raw_rows: list[list[Any]],
    max_preview_rows: int,
) -> tuple[ParsedPage, ParsedTable]:
    non_empty_rows: list[list[Any]] = []
    for row in raw_rows:
        serialized = [_serialize_cell(cell) for cell in row]
        if any(str(cell).strip() != "" for cell in serialized):
            non_empty_rows.append(serialized)

    if not non_empty_rows:
        return (
            ParsedPage(
                page_number=page_number,
                text="",
                source="text_layer",
                ocr_confidence=None,
            ),
            ParsedTable(name=sheet_name, columns=[], rows=[]),
        )

    num_cols = max(len(r) for r in non_empty_rows)
    columns = _normalize_header(non_empty_rows[0], num_cols)

    data_rows: list[list[Any]] = []
    for r in non_empty_rows[1:]:
        padded = list(r) + [""] * (num_cols - len(r))
        data_rows.append(padded[:num_cols])

    preview_rows = data_rows[:max_preview_rows]

    text_lines = ["\t".join(columns)]
    for r in preview_rows:
        text_lines.append("\t".join(str(c) for c in r))

    page = ParsedPage(
        page_number=page_number,
        text="\n".join(text_lines),
        source="text_layer",
        ocr_confidence=None,
    )
    table = ParsedTable(
        name=sheet_name,
        columns=columns,
        rows=preview_rows,
    )
    return page, table


def parse_xlsx(file_path: Path) -> ParsedDocument:
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise DocumentParseError("XLSX file is missing or empty")

    try:
        wb = openpyxl.load_workbook(
            filename=str(file_path),
            read_only=True,
            data_only=True,
        )
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise DocumentParseError(f"Corrupt or invalid XLSX file: {exc}") from exc
    except Exception as exc:
        raise DocumentParseError(f"Failed to open XLSX file: {exc}") from exc

    try:
        sheet_names = list(wb.sheetnames)
        if not sheet_names:
            raise DocumentParseError("XLSX workbook contains no sheets")

        pages: list[ParsedPage] = []
        tables: list[ParsedTable] = []
        max_rows = settings.MAX_PREVIEW_ROWS

        for idx, sheet_name in enumerate(sheet_names):
            sheet = wb[sheet_name]
            raw_rows: list[list[Any]] = []
            try:
                for row in sheet.iter_rows(values_only=True):
                    raw_rows.append(list(row))
            except Exception as exc:
                raise DocumentParseError(
                    f"Corrupt sheet '{sheet_name}' in XLSX file: {exc}"
                ) from exc

            page, table = _build_sheet_artifacts(
                sheet_name=sheet_name,
                page_number=idx + 1,
                raw_rows=raw_rows,
                max_preview_rows=max_rows,
            )
            pages.append(page)
            tables.append(table)

        return ParsedDocument(
            pages=pages,
            tables=tables,
            metadata={"sheet_count": len(sheet_names), "format": "xlsx"},
            ocr_used=False,
        )
    finally:
        wb.close()


def _decode_csv_bytes(raw_bytes: bytes) -> tuple[str, str]:
    if not raw_bytes:
        raise DocumentParseError("CSV file is empty")
    if b"\x00" in raw_bytes:
        raise DocumentParseError("Corrupt CSV file (contains binary null bytes)")

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            return text, encoding
        except UnicodeDecodeError:
            continue

    raise DocumentParseError("Unable to decode CSV file with supported encodings")


def parse_csv(file_path: Path) -> ParsedDocument:
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise DocumentParseError("CSV file is missing or empty")

    try:
        raw_bytes = file_path.read_bytes()
    except OSError as exc:
        raise DocumentParseError(f"Failed to read CSV file: {exc}") from exc

    text, encoding_used = _decode_csv_bytes(raw_bytes)
    if not text.strip():
        raise DocumentParseError("CSV file contains no data")

    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    try:
        reader = csv.reader(StringIO(text), delimiter=delimiter)
        raw_rows = [list(row) for row in reader]
    except csv.Error as exc:
        raise DocumentParseError(f"Corrupt CSV structure: {exc}") from exc

    sheet_name = file_path.stem or "csv"
    page, table = _build_sheet_artifacts(
        sheet_name=sheet_name,
        page_number=1,
        raw_rows=raw_rows,
        max_preview_rows=settings.MAX_PREVIEW_ROWS,
    )

    return ParsedDocument(
        pages=[page],
        tables=[table],
        metadata={
            "sheet_count": 1,
            "format": "csv",
            "encoding": encoding_used,
            "delimiter": delimiter,
        },
        ocr_used=False,
    )
