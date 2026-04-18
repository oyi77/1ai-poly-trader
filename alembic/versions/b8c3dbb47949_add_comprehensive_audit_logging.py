"""add_comprehensive_audit_logging

Revision ID: b8c3dbb47949
Revises: 68beef868df4
Create Date: 2026-04-19 01:37:26.445844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c3dbb47949'
down_revision: Union[str, Sequence[str], None] = '68beef868df4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_log', sa.Column('event_type', sa.String(), nullable=True))
    op.add_column('audit_log', sa.Column('entity_type', sa.String(), nullable=True))
    op.add_column('audit_log', sa.Column('entity_id', sa.String(), nullable=True))
    op.add_column('audit_log', sa.Column('old_value', sa.JSON(), nullable=True))
    op.add_column('audit_log', sa.Column('new_value', sa.JSON(), nullable=True))
    op.add_column('audit_log', sa.Column('user_id', sa.String(), nullable=True))
    
    op.create_index('ix_audit_log_timestamp', 'audit_log', ['timestamp'])
    op.create_index('ix_audit_log_event_type', 'audit_log', ['event_type'])
    op.create_index('ix_audit_log_entity_id', 'audit_log', ['entity_id'])
    
    op.execute("UPDATE audit_log SET event_type = action WHERE event_type IS NULL")
    op.execute("UPDATE audit_log SET entity_type = 'SYSTEM' WHERE entity_type IS NULL")
    op.execute("UPDATE audit_log SET entity_id = CAST(id AS TEXT) WHERE entity_id IS NULL")
    op.execute("UPDATE audit_log SET user_id = actor WHERE user_id IS NULL")
    
    op.alter_column('audit_log', 'event_type', nullable=False)
    op.alter_column('audit_log', 'entity_type', nullable=False)
    op.alter_column('audit_log', 'entity_id', nullable=False)


def downgrade() -> None:
    op.drop_index('ix_audit_log_entity_id', 'audit_log')
    op.drop_index('ix_audit_log_event_type', 'audit_log')
    op.drop_index('ix_audit_log_timestamp', 'audit_log')
    
    op.drop_column('audit_log', 'user_id')
    op.drop_column('audit_log', 'new_value')
    op.drop_column('audit_log', 'old_value')
    op.drop_column('audit_log', 'entity_id')
    op.drop_column('audit_log', 'entity_type')
    op.drop_column('audit_log', 'event_type')


def downgrade() -> None:
    """Downgrade schema."""
    pass
