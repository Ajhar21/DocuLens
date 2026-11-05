from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional

from app.models.parse_result import DocumentParseResult


@dataclass(frozen=True)
class ChunkSpec:
    chunk_index: int
    page_number: Optional[int]
    content: str


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _split_oversized_unit(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Hard-split a single oversized segment while respecting word boundaries where possible."""
    pieces: list[str] = []
    step = max(1, target_chars - max(0, overlap_chars))
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + target_chars)
        if end < length:
            # Try to break at the last whitespace within the window
            ws_pos = text.rfind(" ", start + max(1, target_chars // 2), end)
            if ws_pos != -1 and ws_pos > start:
                end = ws_pos
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        next_start = max(start + 1, end - overlap_chars)
        # Align next_start to a word boundary if possible
        if 0 < next_start < length and not text[next_start].isspace():
            space_after = text.find(" ", next_start, min(length, next_start + 40))
            if space_after != -1 and space_after < end:
                next_start = space_after + 1
        start = next_start
    return pieces


def _break_into_units(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Split text into paragraph/sentence units no larger than target_chars."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[str] = []
    for para in paragraphs:
        if len(para) <= target_chars:
            units.append(para)
            continue
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(para) if s.strip()]
        for sent in sentences:
            if len(sent) <= target_chars:
                units.append(sent)
            else:
                units.extend(_split_oversized_unit(sent, target_chars, overlap_chars))
    return units


def chunk_page_text(
    text: str,
    target_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[str]:
    """Paragraph and sentence-aware chunker (~1000 chars with ~150 char overlap)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= target_chars:
        return [cleaned]

    units = _break_into_units(cleaned, target_chars=target_chars, overlap_chars=overlap_chars)
    if not units:
        return []

    chunks: list[str] = []
    current_units: list[str] = []
    current_len = 0

    for unit in units:
        sep_len = 2 if current_units else 0
        if current_units and (current_len + sep_len + len(unit) > target_chars):
            chunk_str = "\n\n".join(current_units).strip()
            if chunk_str:
                chunks.append(chunk_str)

            # Build overlap tail (~overlap_chars) from the end of current_units
            overlap_units: list[str] = []
            overlap_len = 0
            for prev_unit in reversed(current_units):
                added = len(prev_unit) + (2 if overlap_units else 0)
                if overlap_len + added > overlap_chars:
                    break
                overlap_units.insert(0, prev_unit)
                overlap_len += added

            # If no whole unit fit within overlap_chars, take trailing ~overlap_chars from chunk_str
            if not overlap_units and overlap_chars > 0 and chunk_str:
                raw_tail = chunk_str[-overlap_chars:]
                ws_idx = raw_tail.find(" ")
                tail = raw_tail[ws_idx + 1 :].strip() if ws_idx != -1 else raw_tail.strip()
                if not tail:
                    tail = raw_tail.strip()
                if tail and tail != unit:
                    overlap_units = [tail]
                    overlap_len = len(tail)

            current_units = overlap_units
            current_len = len("\n\n".join(current_units))
            sep_len = 2 if current_units else 0
            if current_units and (current_len + sep_len + len(unit) > target_chars):
                current_units = []
                current_len = 0
                sep_len = 0

        current_units.append(unit)
        current_len += sep_len + len(unit)

    if current_units:
        final_chunk = "\n\n".join(current_units).strip()
        if final_chunk and (not chunks or final_chunk != chunks[-1]):
            chunks.append(final_chunk)

    return chunks


def chunk_spreadsheet_tables(
    tables: list[dict[str, Any]],
    target_chars: int = 1000,
) -> list[ChunkSpec]:
    """Group spreadsheet rows into ~1000-char chunks where every chunk starts with
    'Sheet: <name>' and the column header line, and no row is ever split across chunks.
    """
    specs: list[ChunkSpec] = []
    global_idx = 0

    for idx, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        sheet_name = str(table.get("name") or f"Sheet_{idx + 1}").strip()
        raw_cols = table.get("columns") or []
        raw_rows = table.get("rows") or []

        columns = [str(c).strip() for c in raw_cols if c is not None]
        header_line = "\t".join(columns)

        row_lines: list[str] = []
        for row in raw_rows:
            if not isinstance(row, list):
                continue
            serialized_cells = ["" if cell is None else str(cell) for cell in row]
            if not any(c.strip() for c in serialized_cells):
                continue
            row_lines.append("\t".join(serialized_cells))

        if not columns and not row_lines:
            continue

        prefix = f"Sheet: {sheet_name}\n{header_line}" if header_line else f"Sheet: {sheet_name}"

        if not row_lines:
            specs.append(
                ChunkSpec(
                    chunk_index=global_idx,
                    page_number=None,
                    content=prefix,
                )
            )
            global_idx += 1
            continue

        current_rows: list[str] = []
        current_len = len(prefix)

        for r_line in row_lines:
            candidate_len = current_len + 1 + len(r_line)
            if current_rows and candidate_len > target_chars:
                chunk_text = prefix + "\n" + "\n".join(current_rows)
                specs.append(
                    ChunkSpec(
                        chunk_index=global_idx,
                        page_number=None,
                        content=chunk_text,
                    )
                )
                global_idx += 1
                current_rows = [r_line]
                current_len = len(prefix) + 1 + len(r_line)
            else:
                current_rows.append(r_line)
                current_len = candidate_len

        if current_rows:
            chunk_text = prefix + "\n" + "\n".join(current_rows)
            specs.append(
                ChunkSpec(
                    chunk_index=global_idx,
                    page_number=None,
                    content=chunk_text,
                )
            )
            global_idx += 1

    return specs


def chunk_document_content(
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    doc_metadata: Optional[dict[str, Any]] = None,
    target_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[ChunkSpec]:
    """Pure function that chunks parsed document content from DocumentParseResult fields."""
    meta = doc_metadata or {}
    doc_format = str(meta.get("format") or "").lower()

    if doc_format in ("csv", "xlsx") or (tables and not pages):
        return chunk_spreadsheet_tables(tables=tables, target_chars=target_chars)

    sorted_pages = sorted(
        [p for p in pages if isinstance(p, dict)],
        key=lambda p: int(p.get("page_number", 0) or 0),
    )

    specs: list[ChunkSpec] = []
    global_idx = 0
    for idx, page in enumerate(sorted_pages):
        page_num = int(page.get("page_number") or (idx + 1))
        page_text = str(page.get("text") or "").strip()
        if not page_text:
            continue

        page_chunks = chunk_page_text(
            text=page_text,
            target_chars=target_chars,
            overlap_chars=overlap_chars,
        )
        for chunk_str in page_chunks:
            if not chunk_str.strip():
                continue
            specs.append(
                ChunkSpec(
                    chunk_index=global_idx,
                    page_number=page_num,
                    content=chunk_str,
                )
            )
            global_idx += 1

    return specs


def chunk_parse_result(
    parse_result: DocumentParseResult,
    target_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[ChunkSpec]:
    pages = parse_result.pages if isinstance(parse_result.pages, list) else []
    tables = parse_result.tables if isinstance(parse_result.tables, list) else []
    meta = parse_result.doc_metadata if isinstance(parse_result.doc_metadata, dict) else {}
    return chunk_document_content(
        pages=pages,
        tables=tables,
        doc_metadata=meta,
        target_chars=target_chars,
        overlap_chars=overlap_chars,
    )

