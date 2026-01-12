"""create meetings tables

Revision ID: b1c2d3e4f5g6
Revises: a8c94d2f2887
Create Date: 2026-01-10 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5g6"
down_revision: Union[str, None] = "a8c94d2f2887"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create meetings table
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("audio_file_path", sa.String(500), nullable=False),
        sa.Column("audio_duration", sa.Float(), nullable=True),
        sa.Column("audio_format", sa.String(20), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    
    # Create transcriptions table
    op.create_table(
        "transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    
    # Create meeting_topics table
    op.create_table(
        "meeting_topics",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic_name", sa.String(255), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    
    # Create decisions table
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    
    # Create action_items table
    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("assignee", sa.String(255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    
    # Create indexes
    op.create_index("ix_meetings_user_id", "meetings", ["user_id"])
    op.create_index("ix_meetings_status", "meetings", ["status"])
    op.create_index("ix_meeting_topics_meeting_id", "meeting_topics", ["meeting_id"])
    op.create_index("ix_decisions_meeting_id", "decisions", ["meeting_id"])
    op.create_index("ix_action_items_meeting_id", "action_items", ["meeting_id"])


def downgrade():
    op.drop_index("ix_action_items_meeting_id", "action_items")
    op.drop_index("ix_decisions_meeting_id", "decisions")
    op.drop_index("ix_meeting_topics_meeting_id", "meeting_topics")
    op.drop_index("ix_meetings_status", "meetings")
    op.drop_index("ix_meetings_user_id", "meetings")
    op.drop_table("action_items")
    op.drop_table("decisions")
    op.drop_table("meeting_topics")
    op.drop_table("transcriptions")
    op.drop_table("meetings")
