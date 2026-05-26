"""Make flutter_uid nullable in clients

Revision ID: 010_flutter_uid_nullable
Revises: 009_add_plato_tags
Create Date: 2026-05-26

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '010_flutter_uid_nullable'
down_revision: Union[str, None] = '009_add_plato_tags'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('clients', 'flutter_uid', nullable=True)


def downgrade() -> None:
    op.alter_column('clients', 'flutter_uid', nullable=False)
