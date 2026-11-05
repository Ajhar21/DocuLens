"""Day 3 Module 1: review workflow columns and extended review_status check constraint.

Revision ID: 0004_day3_review
Revises: 0003_day3_rbac_audit
Create Date: 2026-11-05 01:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_day3_review"
down_revision: Union[str, None] = "0003_day3_rbac_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add reviewed_by and reviewed_at columns to documents table
    op.add_column(
        "documents",
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_documents_reviewed_by", "documents", ["reviewed_by"], unique=False)

    # 2. Update ck_documents_review_status constraint to include 'in_review' and 'corrected'
    op.drop_constraint("ck_documents_review_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_review_status",
        "documents",
        "review_status IN ('pending', 'needs_review', 'in_review', 'corrected', 'approved', 'rejected', 'not_required')",
    )


def downgrade() -> None:
    # Revert review_status values that are not in the old constraint before adding it back
    op.execute(
        """
        UPDATE documents
        SET review_status = 'pending'
        WHERE review_status IN ('in_review', 'corrected');
        """
    )
    op.drop_constraint("ck_documents_review_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_review_status",
        "documents",
        "review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'not_required')",
    )

    op.drop_index("ix_documents_reviewed_by", table_name="documents")
    op.drop_column("documents", "reviewed_at")
    op.drop_column("documents", "reviewed_by")

