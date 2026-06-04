"""Make metodo_pago nullable in pagos

Revision ID: 012_pago_metodo_nullable
Revises: 011_add_phone_to_clients
Create Date: 2026-06-04

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '012_pago_metodo_nullable'
down_revision: Union[str, None] = '011_add_phone_to_clients'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('pagos', 'metodo_pago', nullable=True)


def downgrade() -> None:
    op.alter_column('pagos', 'metodo_pago', nullable=False)
