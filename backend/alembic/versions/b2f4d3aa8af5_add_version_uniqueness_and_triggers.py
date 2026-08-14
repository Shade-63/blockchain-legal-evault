"""add_version_uniqueness_and_triggers

Revision ID: b2f4d3aa8af5
Revises: 178be4ecf353
Create Date: 2026-08-12 22:08:01.230229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f4d3aa8af5'
down_revision: Union[str, None] = '178be4ecf353'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add idempotency_key column
    op.add_column("document_versions", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_unique_constraint("uq_document_versions_idempotency_key", "document_versions", ["idempotency_key"])

    # 2. Add composite unique constraint
    op.create_unique_constraint(
        "uq_document_versions_doc_id_version_number",
        "document_versions",
        ["document_id", "version_number"]
    )

    # 3. Add PL/pgSQL function to block updates/deletes on core fields
    op.execute("""
        CREATE OR REPLACE FUNCTION block_version_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NEW.id IS DISTINCT FROM OLD.id OR
                   NEW.document_id IS DISTINCT FROM OLD.document_id OR
                   NEW.version_number IS DISTINCT FROM OLD.version_number OR
                   NEW.object_key IS DISTINCT FROM OLD.object_key OR
                   NEW.sha256_hash IS DISTINCT FROM OLD.sha256_hash OR
                   NEW.file_size IS DISTINCT FROM OLD.file_size OR
                   NEW.mime_type IS DISTINCT FROM OLD.mime_type OR
                   NEW.created_by IS DISTINCT FROM OLD.created_by OR
                   NEW.parent_version_id IS DISTINCT FROM OLD.parent_version_id OR
                   NEW.created_at IS DISTINCT FROM OLD.created_at OR
                   NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
                    RAISE EXCEPTION 'DocumentVersion core files/lineage fields are immutable and cannot be updated.';
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DocumentVersion records are read-only and cannot be deleted.';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 4. Add BEFORE UPDATE and BEFORE DELETE triggers
    op.execute("""
        CREATE TRIGGER trigger_block_version_update
        BEFORE UPDATE ON document_versions
        FOR EACH ROW EXECUTE FUNCTION block_version_mutation();
    """)
    op.execute("""
        CREATE TRIGGER trigger_block_version_delete
        BEFORE DELETE ON document_versions
        FOR EACH ROW EXECUTE FUNCTION block_version_mutation();
    """)


def downgrade() -> None:
    # 1. Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trigger_block_version_delete ON document_versions;")
    op.execute("DROP TRIGGER IF EXISTS trigger_block_version_update ON document_versions;")

    # 2. Drop function
    op.execute("DROP FUNCTION IF EXISTS block_version_mutation();")

    # 3. Drop constraints
    op.drop_constraint("uq_document_versions_doc_id_version_number", "document_versions", type_="unique")
    op.drop_constraint("uq_document_versions_idempotency_key", "document_versions", type_="unique")
    op.drop_column("document_versions", "idempotency_key")
