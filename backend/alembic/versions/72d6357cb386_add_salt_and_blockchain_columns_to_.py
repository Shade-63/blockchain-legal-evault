"""add salt and blockchain columns to grants

Revision ID: 72d6357cb386
Revises: cb0fab1a10b2
Create Date: 2026-08-13 21:51:41.962198

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72d6357cb386'
down_revision: Union[str, None] = 'cb0fab1a10b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add salt as nullable first to allow populating existing rows
    op.add_column('document_access_grants', sa.Column('salt', sa.String(), nullable=True))
    op.execute("UPDATE document_access_grants SET salt = md5(random()::text)")
    op.alter_column('document_access_grants', 'salt', nullable=False)
    
    # Add blockchain tracking columns
    op.add_column('document_access_grants', sa.Column('blockchain_status', sa.String(), server_default='confirmed', nullable=False))
    op.add_column('document_access_grants', sa.Column('blockchain_tx_hash', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('document_access_grants', 'blockchain_tx_hash')
    op.drop_column('document_access_grants', 'blockchain_status')
    op.drop_column('document_access_grants', 'salt')
