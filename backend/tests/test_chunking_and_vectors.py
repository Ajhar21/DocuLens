from __future__ import annotations

import math
import pytest

from app.ai.base import (
    PermanentAIError,
    l2_normalize_vector,
    validate_and_normalize_embeddings,
)
from app.ai.fake import FakeEmbeddingProvider
from app.core.config import MIGRATION_EMBEDDING_DIM, Settings
from app.embeddings.chunker import chunk_document_content


def test_chunk_pdf_pages_overlap_empty_skip_and_page_number() -> None:
    para1 = "Alpha invoice header details. " * 20  # ~600 chars
    para2 = "Beta line item specifications and terms. " * 20  # ~820 chars
    page1_text = f"{para1.strip()}\n\n{para2.strip()}"

    pages = [
        {"page_number": 1, "text": page1_text, "source": "text_layer"},
        {"page_number": 2, "text": "   \n  ", "source": "text_layer"},  # empty page skipped
        {"page_number": 3, "text": "Page three summary total.", "source": "ocr"},
    ]

    chunks = chunk_document_content(
        pages=pages,
        tables=[],
        doc_metadata={"format": "pdf"},
        target_chars=1000,
        overlap_chars=150,
    )

    assert len(chunks) >= 3
    # Global sequential chunk_index
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Page 1 chunks have page_number=1, Page 3 chunk has page_number=3, empty page 2 is skipped
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 1
    assert chunks[-1].page_number == 3
    # Overlap check between chunk 0 and chunk 1 on page 1
    tail_snippet = chunks[0].content[-80:]
    assert tail_snippet in chunks[1].content


def test_chunk_spreadsheet_tables_header_on_every_chunk_and_no_row_split() -> None:
    rows = [[f"INV-{i:04d}", f"Supplier Name {i}", f"{i * 100}.00"] for i in range(1, 45)]
    tables = [
        {
            "name": "Invoices_Q1",
            "columns": ["invoice_no", "supplier", "amount"],
            "rows": rows,
        },
        {
            "name": "EmptySheet",
            "columns": [],
            "rows": [],
        },
    ]

    chunks = chunk_document_content(
        pages=[],
        tables=tables,
        doc_metadata={"format": "xlsx"},
        target_chars=400,
    )

    assert len(chunks) > 2
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    expected_header_prefix = "Sheet: Invoices_Q1\ninvoice_no\tsupplier\tamount\n"
    reconstructed_rows: list[str] = []
    for chunk in chunks:
        # Spreadsheets must have page_number = None
        assert chunk.page_number is None
        # Every chunk must start with "Sheet: <name>" and the column header line
        assert chunk.content.startswith(expected_header_prefix)
        body_lines = chunk.content[len(expected_header_prefix) :].splitlines()
        assert len(body_lines) >= 1
        for line in body_lines:
            # Verify no row was split across chunks (always 3 tab-separated columns)
            assert len(line.split("\t")) == 3
            reconstructed_rows.append(line)

    assert len(reconstructed_rows) == len(rows)


def test_vector_l2_normalization_and_count_length_assertions() -> None:
    vec = l2_normalize_vector([3.0, 4.0] + [0.0] * (MIGRATION_EMBEDDING_DIM - 2))
    assert len(vec) == MIGRATION_EMBEDDING_DIM
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)
    assert math.isclose(vec[0], 0.6, rel_tol=1e-6)
    assert math.isclose(vec[1], 0.8, rel_tol=1e-6)

    # Count mismatch must raise PermanentAIError loudly
    with pytest.raises(PermanentAIError, match="count mismatch"):
        validate_and_normalize_embeddings(
            raw_vectors=[[1.0] * MIGRATION_EMBEDDING_DIM],
            expected_count=2,
            expected_dim=MIGRATION_EMBEDDING_DIM,
        )

    # Dimension mismatch must raise PermanentAIError loudly
    with pytest.raises(PermanentAIError, match="dimension mismatch"):
        validate_and_normalize_embeddings(
            raw_vectors=[[1.0, 2.0, 3.0]],
            expected_count=1,
            expected_dim=MIGRATION_EMBEDDING_DIM,
        )

    # FakeEmbeddingProvider produces deterministic L2-normalized vectors of EMBEDDING_DIM
    fake_emb = FakeEmbeddingProvider()
    vecs = fake_emb.embed_documents(["Chunk one", "Chunk two"])
    assert len(vecs) == 2
    for v in vecs:
        assert len(v) == MIGRATION_EMBEDDING_DIM
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_settings_startup_fails_fast_on_wrong_embedding_dim_or_latest_alias() -> None:
    with pytest.raises(ValueError, match="EMBEDDING_DIM"):
        Settings(
            DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/db",
            JWT_SECRET="secret",
            ADMIN_EMAIL="a@b.com",
            ADMIN_PASSWORD="pass",
            EMBEDDING_DIM=1536,
        )

    with pytest.raises(ValueError, match="-latest"):
        Settings(
            DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/db",
            JWT_SECRET="secret",
            ADMIN_EMAIL="a@b.com",
            ADMIN_PASSWORD="pass",
            LLM_MODEL="gemini-flash-latest",
        )

