"""Add phone column to clients

Revision ID: 011_add_phone_to_clients
Revises: 010_flutter_uid_nullable
Create Date: 2026-06-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '011_add_phone_to_clients'
down_revision: Union[str, None] = '010_flutter_uid_nullable'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('phone', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'phone')
