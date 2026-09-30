"""Private portraits, versioned video tasks and video delivery receipts."""

import sqlalchemy as sa
from alembic import op

revision = 'c312e09b4a71'
down_revision = 'a71d90ce2401'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'video_studio',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    for key in ('user_id', 'kind', 'status'):
        op.create_index(f'ix_video_studio_{key}', 'video_studio', [key])


def downgrade():
    op.drop_table('video_studio')
