"""Add budget_level and meal_style to platos

Revision ID: 009_add_plato_tags
Revises: d07b43e35f9a
Create Date: 2026-05-25

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "009_add_plato_tags"
down_revision: Union[str, Sequence[str], None] = "d07b43e35f9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platos", sa.Column("budget_level", sa.String(20), nullable=True))
    op.add_column("platos", sa.Column("meal_style",   sa.String(50), nullable=True))
    op.create_index("idx_platos_budget",    "platos", ["budget_level"])
    op.create_index("idx_platos_style",     "platos", ["meal_style"])
    op.create_index("idx_platos_tipo",      "platos", ["tipo_plato"])


def downgrade() -> None:
    op.drop_index("idx_platos_tipo",   table_name="platos")
    op.drop_index("idx_platos_style",  table_name="platos")
    op.drop_index("idx_platos_budget", table_name="platos")
    op.drop_column("platos", "meal_style")
    op.drop_column("platos", "budget_level")
