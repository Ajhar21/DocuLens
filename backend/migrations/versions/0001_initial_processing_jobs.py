"""Initial migration: enable extensions and create processing_jobs table.

Revision ID: 0001
Revises: 
Create Date: 2026-11-01 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Create processing_jobs table
    op.create_table(
        "processing_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "job_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "run_after",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "locked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "current_stage",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_type IN ('DOCUMENT_PROCESSING', 'EMBEDDING')",
            name="ck_processing_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_processing_jobs_status",
        ),
    )

    # 3. Create partial index for fast queue polling
    op.create_index(
        "idx_processing_jobs_pending",
        "processing_jobs",
        ["status", "run_after"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # 4. Create partial unique index to guarantee one active job per (document_id, job_type)
    op.create_index(
        "uq_processing_jobs_active_document_job",
        "processing_jobs",
        ["document_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'PROCESSING')"),
    )


def downgrade() -> None:
    # Drop indexes and table ONLY. Do NOT drop vector or pg_trgm extensions.
    op.drop_index(
        "uq_processing_jobs_active_document_job",
        table_name="processing_jobs",
    )
    op.drop_index(
        "idx_processing_jobs_pending",
        table_name="processing_jobs",
    )
    op.drop_table("processing_jobs")

