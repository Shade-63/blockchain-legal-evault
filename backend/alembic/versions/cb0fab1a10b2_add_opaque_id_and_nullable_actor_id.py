"""add_opaque_id_and_nullable_actor_id

Revision ID: cb0fab1a10b2
Revises: 3a5f3ad36ba6
Create Date: 2026-08-13 12:50:04.812546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb0fab1a10b2'
down_revision: Union[str, None] = '3a5f3ad36ba6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Alter actor_user_id in audit_events to be nullable
    op.alter_column('audit_events', 'actor_user_id',
               existing_type=sa.UUID(),
               nullable=True)
               
    # 2. Add actor_type in audit_events
    op.add_column('audit_events', sa.Column('actor_type', sa.String(), server_default='authenticated', nullable=False))
    
    # 3. Add opaque_verification_id to document_versions as nullable first
    op.add_column('document_versions', sa.Column('opaque_verification_id', sa.UUID(), nullable=True))
    
    # 4. Generate random UUIDs for existing rows in document_versions
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE document_versions SET opaque_verification_id = gen_random_uuid() WHERE opaque_verification_id IS NULL;"))
    
    # 5. Alter opaque_verification_id in document_versions to be nullable=False
    op.alter_column('document_versions', 'opaque_verification_id',
               existing_type=sa.UUID(),
               nullable=False)
               
    # 6. Create unique constraint for opaque_verification_id
    op.create_unique_constraint('uq_document_versions_opaque_id', 'document_versions', ['opaque_verification_id'])


def downgrade() -> None:
    # 1. Drop constraint on opaque_verification_id
    op.drop_constraint('uq_document_versions_opaque_id', 'document_versions', type_='unique')
    
    # 2. Drop opaque_verification_id column
    op.drop_column('document_versions', 'opaque_verification_id')
    
    # 3. Drop actor_type column from audit_events
    op.drop_column('audit_events', 'actor_type')
    
    # 4. Restore actor_user_id nullable=False in audit_events after cleaning public events
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM audit_events WHERE actor_type = 'PUBLIC_VERIFIER' OR actor_user_id IS NULL;"))
    
    op.alter_column('audit_events', 'actor_user_id',
               existing_type=sa.UUID(),
               nullable=False)
