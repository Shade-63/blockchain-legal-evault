"""add_access_grants_and_audit_log

Revision ID: 3a5f3ad36ba6
Revises: b2f4d3aa8af5
Create Date: 2026-08-12 23:37:06.256859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a5f3ad36ba6'
down_revision: Union[str, None] = 'b2f4d3aa8af5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create document_access_grants table
    op.create_table(
        "document_access_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("granted_to_user_id", sa.UUID(), nullable=False),
        sa.Column("granted_by_user_id", sa.UUID(), nullable=False),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id")
    )
    # Composite conditional unique index to prevent duplicate active grants
    op.execute("""
        CREATE UNIQUE INDEX uq_active_grants 
        ON document_access_grants (version_id, granted_to_user_id) 
        WHERE (revoked_at IS NULL);
    """)

    # 2. Create audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("version_id", sa.UUID(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_metadata_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id")
    )

    # 3. Add PL/pgSQL trigger functions for immutability
    op.execute("""
        CREATE OR REPLACE FUNCTION block_grant_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NEW.id IS DISTINCT FROM OLD.id OR
                   NEW.document_id IS DISTINCT FROM OLD.document_id OR
                   NEW.version_id IS DISTINCT FROM OLD.version_id OR
                   NEW.granted_to_user_id IS DISTINCT FROM OLD.granted_to_user_id OR
                   NEW.granted_by_user_id IS DISTINCT FROM OLD.granted_by_user_id OR
                   NEW.permission IS DISTINCT FROM OLD.permission OR
                   NEW.created_at IS DISTINCT FROM OLD.created_at OR
                   NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
                    RAISE EXCEPTION 'DocumentAccessGrant core fields are immutable and cannot be updated.';
                END IF;
                
                IF OLD.revoked_at IS NOT NULL THEN
                    IF NEW.revoked_at IS DISTINCT FROM OLD.revoked_at OR NEW.revoked_at IS NULL THEN
                        RAISE EXCEPTION 'DocumentAccessGrant revoked_at cannot be modified once set.';
                    END IF;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'DocumentAccessGrant records are read-only and cannot be deleted.';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION block_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Audit log entries are write-once and cannot be modified or deleted.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 4. Create BEFORE UPDATE and BEFORE DELETE triggers
    op.execute("""
        CREATE TRIGGER trigger_block_grant_update
        BEFORE UPDATE ON document_access_grants
        FOR EACH ROW EXECUTE FUNCTION block_grant_mutation();
        
        CREATE TRIGGER trigger_block_grant_delete
        BEFORE DELETE ON document_access_grants
        FOR EACH ROW EXECUTE FUNCTION block_grant_mutation();
    """)

    op.execute("""
        CREATE TRIGGER trigger_block_audit_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION block_audit_mutation();
        
        CREATE TRIGGER trigger_block_audit_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION block_audit_mutation();
    """)


def downgrade() -> None:
    # 1. Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trigger_block_audit_delete ON audit_events;")
    op.execute("DROP TRIGGER IF EXISTS trigger_block_audit_update ON audit_events;")
    op.execute("DROP TRIGGER IF EXISTS trigger_block_grant_delete ON document_access_grants;")
    op.execute("DROP TRIGGER IF EXISTS trigger_block_grant_update ON document_access_grants;")

    # 2. Drop functions
    op.execute("DROP FUNCTION IF EXISTS block_audit_mutation();")
    op.execute("DROP FUNCTION IF EXISTS block_grant_mutation();")

    # 3. Drop tables and indexes
    op.drop_table("audit_events")
    op.execute("DROP INDEX IF EXISTS uq_active_grants;")
    op.drop_table("document_access_grants")

