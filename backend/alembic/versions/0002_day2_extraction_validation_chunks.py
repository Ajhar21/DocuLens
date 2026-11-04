"""Day 2 schema: extracted_invoices, invoice_line_items, validation_results, document_corrections, document_chunks, and job/document constraints.

Revision ID: 0002_day2_schema
Revises: 0001_initial_schema
Create Date: 2026-11-04 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.config import MIGRATION_EMBEDDING_DIM

revision: str = "0002_day2_schema"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;")

    # 1. Extend documents table with review_status and CHECK constraints
    op.add_column(
        "documents",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('uploaded', 'processing', 'parsed', 'failed')",
    )
    op.create_check_constraint(
        "ck_documents_review_status",
        "documents",
        "review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'not_required')",
    )

    # 2. Extend processing_jobs table with current_stage, CHECK constraints, and partial UNIQUE index
    op.add_column(
        "processing_jobs",
        sa.Column("current_stage", sa.String(length=100), nullable=True),
    )
    # Deduplicate any pre-existing duplicate active jobs before creating the unique index
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY document_id, job_type
                       ORDER BY created_at DESC, id DESC
                   ) AS rn
            FROM processing_jobs
            WHERE status IN ('pending', 'running')
        )
        UPDATE processing_jobs
        SET status = 'failed',
            last_error = COALESCE(last_error, 'Superseded by newer active job during migration'),
            finished_at = COALESCE(finished_at, now()),
            locked_by = NULL,
            locked_at = NULL
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )
    op.create_check_constraint(
        "ck_processing_jobs_job_type",
        "processing_jobs",
        "job_type IN ('parse', 'extraction', 'embedding')",
    )
    op.create_check_constraint(
        "ck_processing_jobs_status",
        "processing_jobs",
        "status IN ('pending', 'running', 'succeeded', 'failed')",
    )
    op.create_index(
        "uq_processing_jobs_active_doc_type",
        "processing_jobs",
        ["document_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    # 3. Create extracted_invoices table and indexes
    op.create_table(
        "extracted_invoices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("supplier_name", sa.Text(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=True),
        sa.Column("tax", sa.Numeric(19, 4), nullable=True),
        sa.Column("total", sa.Numeric(19, 4), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column(
            "extraction_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_extracted_invoices_invoice_number",
        "extracted_invoices",
        ["invoice_number"],
        unique=False,
    )
    op.create_index(
        "ix_extracted_invoices_invoice_date",
        "extracted_invoices",
        ["invoice_date"],
        unique=False,
    )
    op.create_index(
        "ix_extracted_invoices_total",
        "extracted_invoices",
        ["total"],
        unique=False,
    )
    op.create_index(
        "ix_extracted_invoices_supplier_lower",
        "extracted_invoices",
        [sa.text("lower(supplier_name)")],
        unique=False,
    )
    op.create_index(
        "ix_extracted_invoices_supplier_trgm",
        "extracted_invoices",
        ["supplier_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"supplier_name": "gin_trgm_ops"},
    )

    # 4. Create invoice_line_items table and index
    op.create_table(
        "invoice_line_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extracted_invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=True),
    )
    op.create_index(
        "ix_invoice_line_items_invoice_id",
        "invoice_line_items",
        ["invoice_id"],
        unique=False,
    )

    # 5. Create validation_results table and indexes
    op.create_table(
        "validation_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("validation_code", sa.Text(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "severity IN ('ERROR', 'WARNING', 'INFO')",
            name="ck_validation_results_severity",
        ),
        sa.CheckConstraint(
            "status IN ('PASSED', 'FAILED', 'SKIPPED')",
            name="ck_validation_results_status",
        ),
    )
    op.create_index(
        "ix_validation_results_document_id",
        "validation_results",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_validation_results_validation_code",
        "validation_results",
        ["validation_code"],
        unique=False,
    )

    # 6. Create document_corrections table and index
    op.create_table(
        "document_corrections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extracted_invoices.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column(
            "corrected_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_document_corrections_document_id",
        "document_corrections",
        ["document_id"],
        unique=False,
    )

    # 7. Create document_chunks table and indexes (NO page_id; uses page_number INTEGER NULL)
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "embedding",
            Vector(MIGRATION_EMBEDDING_DIM),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_doc_chunk_idx",
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_content_tsv",
        "document_chunks",
        ["content_tsv"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Enable RLS on all new tables (matching Day 1 security convention)
    op.execute("ALTER TABLE extracted_invoices ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE validation_results ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE document_corrections ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index("ix_document_chunks_content_tsv", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_document_corrections_document_id", table_name="document_corrections")
    op.drop_table("document_corrections")

    op.drop_index("ix_validation_results_validation_code", table_name="validation_results")
    op.drop_index("ix_validation_results_document_id", table_name="validation_results")
    op.drop_table("validation_results")

    op.drop_index("ix_invoice_line_items_invoice_id", table_name="invoice_line_items")
    op.drop_table("invoice_line_items")

    op.drop_index("ix_extracted_invoices_supplier_trgm", table_name="extracted_invoices")
    op.drop_index("ix_extracted_invoices_supplier_lower", table_name="extracted_invoices")
    op.drop_index("ix_extracted_invoices_total", table_name="extracted_invoices")
    op.drop_index("ix_extracted_invoices_invoice_date", table_name="extracted_invoices")
    op.drop_index("ix_extracted_invoices_invoice_number", table_name="extracted_invoices")
    op.drop_table("extracted_invoices")

    op.drop_index("uq_processing_jobs_active_doc_type", table_name="processing_jobs")
    op.drop_constraint("ck_processing_jobs_status", "processing_jobs", type_="check")
    op.drop_constraint("ck_processing_jobs_job_type", "processing_jobs", type_="check")
    op.drop_column("processing_jobs", "current_stage")

    op.drop_constraint("ck_documents_review_status", "documents", type_="check")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.drop_column("documents", "review_status")

