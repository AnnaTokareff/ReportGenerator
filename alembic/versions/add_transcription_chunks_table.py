"""add transcription_chunks table for embedding cache

Revision ID: c2d3e4f5g6h7
Revises: b1c2d3e4f5g6
Create Date: 2026-01-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5g6h7"
down_revision: Union[str, None] = "b1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create transcription_chunks table for caching embeddings
    op.create_table(
        "transcription_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("transcription_id", sa.Integer(), sa.ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    
    # Create indexes for faster lookups
    op.create_index("ix_transcription_chunks_transcription_id", "transcription_chunks", ["transcription_id"])


def downgrade():
    op.drop_index("ix_transcription_chunks_transcription_id", "transcription_chunks")
    op.drop_table("transcription_chunks")
