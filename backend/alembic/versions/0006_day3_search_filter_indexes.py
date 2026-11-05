"""Day 3 Module 5: search filter and trigram indexes.

Revision ID: 0006_day3_search
Revises: 0005_day3_reconciliation
Create Date: 2026-11-05 02:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_day3_search"
down_revision: Union[str, None] = "0005_day3_reconciliation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Indexes on documents table for structured filters & sorting
    op.create_index("ix_documents_review_status", "documents", ["review_status"])
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    # 2. Additional trigram indexes on extracted_invoices for typo-tolerant keyword search
    op.create_index(
        "ix_extracted_invoices_inv_num_trgm",
        "extracted_invoices",
        ["invoice_number"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"invoice_number": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_extracted_invoices_customer_trgm",
        "extracted_invoices",
        ["customer_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"customer_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_extracted_invoices_customer_trgm", table_name="extracted_invoices")
    op.drop_index("ix_extracted_invoices_inv_num_trgm", table_name="extracted_invoices")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_uploaded_by", table_name="documents")
    op.drop_index("ix_documents_review_status", table_name="documents")

