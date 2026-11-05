"""Day 3 Module 4: reconciliation_jobs and reconciliation_results tables.

Revision ID: 0005_day3_reconciliation
Revises: 0004_day3_review
Create Date: 2026-11-05 01:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_day3_reconciliation"
down_revision: Union[str, None] = "0004_day3_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create reconciliation_jobs table
    op.create_table(
        "reconciliation_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "initiated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id_a",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id_b",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reconciliation_type", sa.String(32), nullable=False),
        sa.Column("overall_status", sa.String(32), nullable=False),
        sa.Column("discrepancy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "initiated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "reconciliation_type IN ('PDF_PDF', 'PDF_EXCEL')",
            name="ck_reconciliation_jobs_type",
        ),
        sa.CheckConstraint(
            "overall_status IN ('MATCHED', 'MISMATCHED', 'ERROR')",
            name="ck_reconciliation_jobs_status",
        ),
    )

    op.create_index("ix_reconciliation_jobs_doc_a", "reconciliation_jobs", ["document_id_a"])
    op.create_index("ix_reconciliation_jobs_doc_b", "reconciliation_jobs", ["document_id_b"])
    op.create_index(
        "ix_reconciliation_jobs_user_initiated",
        "reconciliation_jobs",
        ["initiated_by", "initiated_at"],
    )
    op.create_index(
        "ix_reconciliation_jobs_status",
        "reconciliation_jobs",
        ["overall_status"],
    )

    # 2. Create reconciliation_results table
    op.create_table(
        "reconciliation_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reconciliation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("source_a_value", sa.Text(), nullable=True),
        sa.Column("source_b_value", sa.Text(), nullable=True),
        sa.Column("match_status", sa.String(32), nullable=False),
        sa.Column("absolute_difference", sa.Numeric(19, 4), nullable=True),
        sa.Column("percentage_difference", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('HEADER', 'LINE_ITEM')",
            name="ck_reconciliation_results_entity",
        ),
        sa.CheckConstraint(
            "match_status IN ('EXACT_MATCH', 'TOLERANCE_MATCH', 'MISMATCH', 'MISSING_IN_A', 'MISSING_IN_B', 'NOT_COMPARABLE')",
            name="ck_reconciliation_results_status",
        ),
    )

    op.create_index("ix_reconciliation_results_job_id", "reconciliation_results", ["job_id"])
    op.create_index(
        "ix_reconciliation_results_match_status",
        "reconciliation_results",
        ["match_status"],
    )

    # 3. Enable RLS and bypass policy for service role
    op.execute("ALTER TABLE reconciliation_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE reconciliation_results ENABLE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY p_service_reconciliation_jobs ON reconciliation_jobs "
        "FOR ALL TO PUBLIC USING (true) WITH CHECK (true);"
    )
    op.execute(
        "CREATE POLICY p_service_reconciliation_results ON reconciliation_results "
        "FOR ALL TO PUBLIC USING (true) WITH CHECK (true);"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS p_service_reconciliation_results ON reconciliation_results;")
    op.execute("DROP POLICY IF EXISTS p_service_reconciliation_jobs ON reconciliation_jobs;")
    op.drop_table("reconciliation_results")
    op.drop_table("reconciliation_jobs")

