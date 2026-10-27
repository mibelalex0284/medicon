"""add_consultation_notes_fields

Revision ID: 37d676368ea4
Revises: 62991874a08c
Create Date: 2026-10-27 14:25:54.174146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37d676368ea4'
down_revision: Union[str, Sequence[str], None] = '62991874a08c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add clinical notes, diagnosis, prescriptions, and follow-up fields to consultations."""
    op.add_column('consultations', sa.Column('clinical_notes', sa.Text(), nullable=True, comment='Physician clinical encounter notes'))
    op.add_column('consultations', sa.Column('diagnosis', sa.Text(), nullable=True, comment='Working clinical diagnosis'))
    op.add_column('consultations', sa.Column('prescriptions', sa.Text(), nullable=True, comment='Prescriptions and clinical orders (JSON or formatted text)'))
    op.add_column('consultations', sa.Column('follow_up_instructions', sa.Text(), nullable=True, comment='Follow-up care instructions for patient'))


def downgrade() -> None:
    """Downgrade schema to remove clinical notes fields from consultations."""
    op.drop_column('consultations', 'follow_up_instructions')
    op.drop_column('consultations', 'prescriptions')
    op.drop_column('consultations', 'diagnosis')
    op.drop_column('consultations', 'clinical_notes')

