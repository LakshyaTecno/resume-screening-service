"""add tenancy

Revision ID: 11d5ffa87cbb
Revises: cb36370cdbb9
Create Date: 2026-08-29 16:25:52.290257

Destructive by design: candidates/jobs/match_results predate the tenant
concept, so existing rows have no tenant to belong to and there's no
correct value to backfill. This truncates all three rather than
fabricating a "legacy" owner - acceptable because this is pre-launch data,
confirmed with the user before writing this migration. If real data ever
needs preserving through an equivalent change, back it up first; this
migration does not attempt to.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11d5ffa87cbb"
down_revision: Union[str, Sequence[str], None] = "cb36370cdbb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("hashed_key", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=12), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_api_keys_tenant_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashed_key"),
    )
    op.create_index(op.f("ix_api_keys_tenant_id"), "api_keys", ["tenant_id"], unique=False)

    # See the module docstring: no correct tenant_id exists for pre-existing
    # rows, so they're truncated rather than backfilled to a fabricated
    # "legacy" tenant. Must happen before the NOT NULL columns below are
    # added - Postgres refuses a NOT NULL column with no default on a
    # non-empty table.
    op.execute("TRUNCATE TABLE match_results, candidates, jobs")

    op.add_column("candidates", sa.Column("tenant_id", sa.UUID(), nullable=False))
    op.create_index(op.f("ix_candidates_tenant_id"), "candidates", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "fk_candidates_tenant_id",
        "candidates",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("jobs", sa.Column("tenant_id", sa.UUID(), nullable=False))
    op.create_index(op.f("ix_jobs_tenant_id"), "jobs", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_tenant_id", "jobs", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_tenant_id", "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_tenant_id"), table_name="jobs")
    op.drop_column("jobs", "tenant_id")

    op.drop_constraint("fk_candidates_tenant_id", "candidates", type_="foreignkey")
    op.drop_index(op.f("ix_candidates_tenant_id"), table_name="candidates")
    op.drop_column("candidates", "tenant_id")

    op.drop_index(op.f("ix_api_keys_tenant_id"), table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("tenants")
