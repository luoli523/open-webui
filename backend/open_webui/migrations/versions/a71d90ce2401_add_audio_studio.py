"""Persist audio studio jobs and delivery receipts."""

import sqlalchemy as sa
from alembic import op

revision = 'a71d90ce2401'
down_revision = 'd4c1a8e37b62'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audio_studio',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    for key in ('user_id', 'kind', 'status'):
        op.create_index(f'ix_audio_studio_{key}', 'audio_studio', [key])


def downgrade():
    op.drop_table('audio_studio')
