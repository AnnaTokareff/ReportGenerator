"""
Models:
- Meeting: Main meeting metadata and audio file info
- Transcription: Transcribed text from meetings
- TranscriptionChunk: Text chunks with embeddings for semantic search
- MeetingTopic: Extracted topics from meetings
- Decision: Decisions made during meetings
- ActionItem: Action items extracted from meetings
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
    LargeBinary,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class MeetingStatus(str, Enum):
    """Meet processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionItemStatus(str, Enum):
    """Task status"""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActionItemPriority(str, Enum):
    """Task priority"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Meeting(Base):
    """
    Meeting model - stores meeting metadata and audio file information
    
    1) User uploads audio file -> meeting created with status=PENDING
    2) Background task starts -> status=PROCESSING
    3) Transcription completes -> status=COMPLETED
    4) If error occurs -> status=FAILED
    """
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # audio file info
    audio_file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # duration
    audio_format: Mapped[str | None] = mapped_column(String(10), nullable=True)  
    
    # processing status
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  
    status: Mapped[MeetingStatus] = mapped_column(
        SQLEnum(MeetingStatus),
        default=MeetingStatus.PENDING,
        nullable=False,
        index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="meetings")
    transcription: Mapped["Transcription | None"] = relationship(
        "Transcription",
        back_populates="meeting",
        uselist=False,
        cascade="all, delete-orphan"
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

    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, title='{self.title}', status='{self.status}')>"


class Transcription(Base):
    """
    Transcription model - stores transcribed text from audio
    
    This is the text that will be:
    1) Indexed for semantic search
    2) Used to extract summaries, topics, decisions, action items
    3) Referenced when answering support queries
    """
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    
    # transcription content
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    #  metadata
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    
    # segments with timestamps in json
    # [{"start": 0.0, "end": 5.2, "text": "Hello everyone", "speaker": "Speaker 1"}]
    # or dict format 
    segments: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    
    # timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="transcription")
    chunks: Mapped[list["TranscriptionChunk"]] = relationship(
        "TranscriptionChunk",
        back_populates="transcription",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Transcription(id={self.id}, meeting_id={self.meeting_id}, language='{self.language}')>"


class TranscriptionChunk(Base):
    """
    Caches text chunks with embeddings for semantic search.
    It has:
    - Split transcription text into chunks
    - Pre-computed embeddings for each chunk
    - Used for fast semantic search in Rag assistant
    
    """
    __tablename__ = "transcription_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  #  chunk number
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)  # text of the chunk
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # pickled numpy array
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # relationships
    transcription: Mapped["Transcription"] = relationship("Transcription", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<TranscriptionChunk(id={self.id}, transcription_id={self.transcription_id}, chunk_index={self.chunk_index})>"


class MeetingTopic(Base):
    """
    Stores extracted topics from meeting transcriptions
    """
    __tablename__ = "meeting_topics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    topic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relevance_score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False
    )  # relevance score (0.0 to 1.0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="topics")

    def __repr__(self) -> str:
        return f"<MeetingTopic(id={self.id}, topic_name='{self.topic_name}', relevance={self.relevance_score})>"


class Decision(Base):
    """
    Stores decisions made during meetings
    """
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  
    
    # Store participants as json list
    participants: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="decisions")

    def __repr__(self) -> str:
        return f"<Decision(id={self.id}, meeting_id={self.meeting_id})>"


class ActionItem(Base):
    """
    Stores action items extracted from meetings
    
    Action items are:
    - Tasks assigned during meetings
    - Tracked for completion
    - Referenced in support queries
    """
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)  # who is assigned the task
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # deadline
    
    priority: Mapped[ActionItemPriority] = mapped_column(
        SQLEnum(ActionItemPriority),
        default=ActionItemPriority.MEDIUM,
        nullable=False
    )
    status: Mapped[ActionItemStatus] = mapped_column(
        SQLEnum(ActionItemStatus),
        default=ActionItemStatus.TODO,
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="action_items")

    def __repr__(self) -> str:
        return f"<ActionItem(id={self.id}, assignee='{self.assignee}', status='{self.status}')>"