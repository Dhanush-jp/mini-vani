"""Add cgpa and sgpa columns to students

Revision ID: 8c3d4f1a2b67
Revises: 3e05e4b8e406
Create Date: 2026-03-31 01:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c3d4f1a2b67"
down_revision: Union[str, Sequence[str], None] = "3e05e4b8e406"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("students")}

    with op.batch_alter_table("students") as batch_op:
        if "cgpa" not in existing_columns:
            batch_op.add_column(sa.Column("cgpa", sa.Float(), nullable=False, server_default=sa.text("0.0")))
        if "sgpa" not in existing_columns:
            batch_op.add_column(sa.Column("sgpa", sa.Float(), nullable=False, server_default=sa.text("0.0")))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("students")}

    with op.batch_alter_table("students") as batch_op:
        if "sgpa" in existing_columns:
            batch_op.drop_column("sgpa")
        if "cgpa" in existing_columns:
            batch_op.drop_column("cgpa")
