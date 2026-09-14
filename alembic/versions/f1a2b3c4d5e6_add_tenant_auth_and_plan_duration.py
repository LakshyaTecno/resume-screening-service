"""add tenant auth and plan duration

Revision ID: f1a2b3c4d5e6
Revises: e0566164803f
Create Date: 2026-09-14 10:00:00.000000

Purely additive: every new column is nullable (or has a server_default
for existing rows), unlike 11d5ffa87cbb's destructive truncate. Existing
admin-created tenants and plans need no backfill - they simply never
populate email/hashed_password/google_sub, and duration_months defaults
to 1 (matching the monthly billing this app has only ever actually used
so far).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e0566164803f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("hashed_password", sa.String(length=255), nullable=True))
    op.add_column("tenants", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_tenants_email", "tenants", ["email"])
    op.create_unique_constraint("uq_tenants_google_sub", "tenants", ["google_sub"])

    op.add_column(
        "plans",
        sa.Column("duration_months", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("plans", "duration_months")
    op.drop_constraint("uq_tenants_google_sub", "tenants", type_="unique")
    op.drop_constraint("uq_tenants_email", "tenants", type_="unique")
    op.drop_column("tenants", "google_sub")
    op.drop_column("tenants", "hashed_password")
    op.drop_column("tenants", "email")
