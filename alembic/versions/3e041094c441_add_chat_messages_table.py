"""add chat_messages table

Revision ID: 3e041094c441
Revises: a3f7c9d81b44
Create Date: 2026-09-24 21:16:46.669215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e041094c441'
down_revision: Union[str, Sequence[str], None] = 'a3f7c9d81b44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('chat_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_client_id'), 'chat_messages', ['client_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_client_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
