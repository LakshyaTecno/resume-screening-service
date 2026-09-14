"""add candidate status and nullable full_name

Revision ID: 6bf8f532381d
Revises: 11d5ffa87cbb
Create Date: 2026-08-29 16:32:16.025643

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bf8f532381d"
down_revision: Union[str, Sequence[str], None] = "11d5ffa87cbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processed"),
    )
    op.alter_column("candidates", "full_name", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.alter_column("candidates", "full_name", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("candidates", "status")
