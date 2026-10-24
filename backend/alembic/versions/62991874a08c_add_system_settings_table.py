"""add_system_settings_table

Revision ID: 62991874a08c
Revises: 51187874a08b
Create Date: 2026-10-24 07:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62991874a08c'
down_revision: Union[str, Sequence[str], None] = '51187874a08b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add system_settings table."""
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=100), nullable=False, comment='Unique identifier for configuration setting'),
        sa.Column('value', sa.String(length=255), nullable=False, comment='String-serialized value of the setting'),
        sa.Column('description', sa.String(length=255), nullable=True, comment='Human-readable description of this setting'),
        sa.Column('updated_by', sa.String(length=36), nullable=True, comment='Profile ID of administrator who updated the setting'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['profiles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_system_settings_key'), 'system_settings', ['key'], unique=False)


def downgrade() -> None:
    """Downgrade schema to remove system_settings table."""
    op.drop_index(op.f('ix_system_settings_key'), table_name='system_settings')
    op.drop_table('system_settings')
