"""
Meeting models for audio transcription and analysis.
- Meeting: Stores meeting metadata and audio file info
- Transcription: Stores the transcribed text from meetings
- MeetingTopic: Stores extracted topics from meetings
- Decision: Stores decisions made during meetings
- ActionItem: Stores action items extracted from meetings
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text, Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class MeetingStatus(str, Enum):
    """Meeting processing status enumeration."""
    PENDING = "pending"  # Just uploaded, not processed yet
    PROCESSING = "processing"  # Currently being transcribed
    COMPLETED = "completed"  # Successfully processed
    FAILED = "failed"  # Processing failed


class ActionItemStatus(str, Enum):
    """Action item status enumeration."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActionItemPriority(str, Enum):
    """Action item priority enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Meeting(Base):
    """
    Meeting model - stores meeting metadata and audio file information.
    1. User uploads audio file -> meeting is created with status=PENDING
    2. Background task starts -> status=PROCESSING
    3. Transcription completes -> status=COMPLETED
    4. If error -> status=FAILED
    """
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Audio file information
    audio_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # in seconds
    audio_format: Mapped[str | None] = mapped_column(String(20), nullable=True)  # mp3, wav, etc.
    
    # Processing status
    status: Mapped[MeetingStatus] = mapped_column(
        SQLEnum(MeetingStatus),
        default=MeetingStatus.PENDING,
        nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Metadata
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="meetings")
    transcription: Mapped["Transcription | None"] = relationship(
        "Transcription",
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False
    )
    topics: Mapped[list["MeetingTopic"]] = relationship(
        "MeetingTopic",
        back_populates="meeting",
        cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        "Decision",
        back_populates="meeting",
        cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        "ActionItem",
        back_populates="meeting",
        cascade="all, delete-orphan"
    )


class Transcription(Base):
    """
    Transcription model - stores the transcribed text from audio.
    
    This is the core text that will be:
    1. Indexed for semantic search
    2. Used to extract summaries, topics, decisions, action items
    3. Referenced when answering support queries
    """
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id"),
        nullable=False,
        unique=True
    )
    
    # Transcription content
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Transcription metadata
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Segments with timestamps (JSON format for flexibility)
    # Format: [{"start": 0.0, "end": 5.2, "text": "Hello everyone", "speaker": "Speaker 1"}]
    # Note: Stored as JSON, can be list or dict depending on format
    segments: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="transcription")


class MeetingTopic(Base):
    """
    MeetingTopic model - stores extracted topics from meeting transcriptions.
    
    Used for:
    - Categorizing meetings
    - Improving search relevance
    - Understanding meeting themes
    """
    __tablename__ = "meeting_topics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    
    topic_name: Mapped[str] = mapped_column(String(100), nullable=False)
    relevance_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0
    )  # 0.0 to 1.0
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="topics")


class Decision(Base):
    """
    Decision model - stores decisions made during meetings.
    
    This is CRITICAL for the support agent:
    - High confidence source (official meeting decision)
    - Can be directly referenced in responses
    - Example: "According to meeting on Jan 15, we decided to increase budget by 20%"
    """
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Store participants as JSON list: ["John Doe", "Jane Smith"]
    participants: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="decisions")


class ActionItem(Base):
    """
    ActionItem model - stores action items extracted from meetings.
    
    Action items are:
    - Tasks assigned during meetings
    - Tracked for completion
    - Referenced in support queries (e.g., "What are my pending tasks?")
    """
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    priority: Mapped[ActionItemPriority] = mapped_column(
        SQLEnum(ActionItemPriority),
        default=ActionItemPriority.MEDIUM,
        nullable=False
    )
    status: Mapped[ActionItemStatus] = mapped_column(
        SQLEnum(ActionItemStatus),
        default=ActionItemStatus.TODO,
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="action_items")