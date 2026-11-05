"""Day 3 Module 0: roles table, users.role_id migration, refresh_tokens, and audit_logs.

Revision ID: 0003_day3_rbac_audit
Revises: 0002_day2_schema
Create Date: 2026-11-05 00:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_day3_rbac_audit"
down_revision: Union[str, None] = "0002_day2_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create roles table and seed 4 canonical roles idempotently
    op.create_table(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "name IN ('FINANCE_EXECUTIVE', 'FINANCE_MANAGER', 'ACCOUNTS_AUDIT', 'SYSTEM_ADMIN')",
            name="ck_roles_name",
        ),
    )

    op.execute(
        """
        INSERT INTO roles (name, description) VALUES
            ('FINANCE_EXECUTIVE', 'Upload and process financial documents, edit extractions, run reconciliation, and search.'),
            ('FINANCE_MANAGER', 'Review and approve/reject manual corrections, view global audit logs, and all Finance Executive capabilities.'),
            ('ACCOUNTS_AUDIT', 'View documents, run and view reconciliations, search documents, and view audit logs.'),
            ('SYSTEM_ADMIN', 'Full system access including user and role management and failed job reprocessing.')
        ON CONFLICT (name) DO NOTHING;
        """
    )

    # 2. Migrate users.role -> users.role_id + add users.updated_at
    op.add_column(
        "users",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Backfill existing users: admin -> SYSTEM_ADMIN, reviewer -> FINANCE_MANAGER, viewer -> ACCOUNTS_AUDIT
    op.execute(
        """
        UPDATE users
        SET role_id = CASE
            WHEN LOWER(role) = 'admin' OR role = 'SYSTEM_ADMIN'
                THEN (SELECT id FROM roles WHERE name = 'SYSTEM_ADMIN')
            WHEN LOWER(role) = 'reviewer' OR role = 'FINANCE_MANAGER'
                THEN (SELECT id FROM roles WHERE name = 'FINANCE_MANAGER')
            WHEN LOWER(role) = 'finance_executive' OR role = 'FINANCE_EXECUTIVE'
                THEN (SELECT id FROM roles WHERE name = 'FINANCE_EXECUTIVE')
            ELSE (SELECT id FROM roles WHERE name = 'ACCOUNTS_AUDIT')
        END;
        """
    )

    op.alter_column("users", "role_id", nullable=False)
    op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)
    op.drop_column("users", "role")

    # 3. Create refresh_tokens table for rotating refresh tokens with reuse detection
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "replaced_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)

    # 4. Create audit_logs table and indexes
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_user_created",
        "audit_logs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
        unique=False,
    )

    # Enable RLS on all new tables
    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'viewer'"),
        ),
    )
    op.execute(
        """
        UPDATE users u
        SET role = CASE r.name
            WHEN 'SYSTEM_ADMIN' THEN 'admin'
            WHEN 'FINANCE_MANAGER' THEN 'reviewer'
            WHEN 'FINANCE_EXECUTIVE' THEN 'reviewer'
            ELSE 'viewer'
        END
        FROM roles r
        WHERE u.role_id = r.id;
        """
    )
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "role_id")

    op.drop_table("roles")

