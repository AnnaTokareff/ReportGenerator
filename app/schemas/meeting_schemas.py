from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.meeting_models import (
    MeetingStatus,
    ActionItemStatus,
    ActionItemPriority
)


# ============================================================================
# ACTION ITEM SCHEMAS
# ============================================================================

class ActionItemBase(BaseModel):
    """Base schema for action items."""
    task_description: str = Field(..., min_length=1, max_length=2000)
    assignee: Optional[str] = Field(None, max_length=255)
    due_date: Optional[datetime] = None
    priority: ActionItemPriority = ActionItemPriority.MEDIUM
    status: ActionItemStatus = ActionItemStatus.TODO


class ActionItemResponse(ActionItemBase):
    """Response schema for action items."""
    id: int
    meeting_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# DECISION SCHEMAS
# ============================================================================

class DecisionBase(BaseModel):
    """Base schema for decisions"""
    decision_text: str = Field(..., min_length=1, max_length=5000)
    context: Optional[str] = Field(None, max_length=5000)
    participants: Optional[list[str]] = None


class DecisionResponse(DecisionBase):
    """Response schema for decisions"""
    id: int
    meeting_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# TOPIC SCHEMAS
# ============================================================================

class TopicResponse(BaseModel):
    """Response schema for meeting topics."""
    id: int
    meeting_id: int
    topic_name: str
    relevance_score: float
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# TRANSCRIPTION SCHEMAS
# ============================================================================

class TranscriptionResponse(BaseModel):
    """Response schema for transcriptions."""
    id: int
    meeting_id: int
    full_text: str
    summary: Optional[str] = None
    language: str
    confidence_score: Optional[float] = None
    segments: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# MEETING SCHEMAS
# ============================================================================

class MeetingCreate(BaseModel):
    """
    Schema for creating a meeting
    """
    title: str = Field(..., min_length=1, max_length=255)
    language: Optional[str] = Field("en", max_length=10)


class MeetingUploadResponse(BaseModel):
    """
    Response after uploading an audio file.
    
    This is the immediate response - transcription is async
    """
    id: int
    title: str
    status: MeetingStatus
    audio_file_path: str
    created_at: datetime
    message: str = "Meeting uploaded successfully. Transcription is in progress..."

    class Config:
        from_attributes = True


class MeetingResponse(BaseModel):
    """
    Complete meeting response with all related data.
    
    Used for GET /meetings/{id} endpoint
    """
    id: int
    user_id: int
    title: str
    audio_file_path: str
    audio_duration: Optional[float] = None
    audio_format: Optional[str] = None
    status: MeetingStatus
    error_message: Optional[str] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    transcription: Optional[TranscriptionResponse] = None
    topics: list[TopicResponse] = []
    decisions: list[DecisionResponse] = []
    action_items: list[ActionItemResponse] = []

    class Config:
        from_attributes = True

class MeetingStatusResponse(BaseModel):
    """
    Response for checking meeting processing status
    
    Used for polling: GET /meetings/{id}/status
    """
    id: int
    status: MeetingStatus
    progress_percentage: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Processing progress (0-100)"
    )
    error_message: Optional[str] = None
    transcription_ready: bool = False

    class Config:
        from_attributes = True


# ============================================================================
# REPORT GENERATION SCHEMAS
# ============================================================================

class ReportGenerateRequest(BaseModel):
    """Request schema for generating meeting report in Markdown format."""
    include_transcription: bool = Field(
        True,
        description="Include full transcription in report"
    )
    include_timestamps: bool = Field(
        False,
        description="Include timestamps in transcription"
    )


class ReportResponse(BaseModel):
    """Response schema for generated Markdown report"""
    meeting_id: int
    content: str = Field(
        ...,
        description="Report content in Markdown format"
    )
    generated_at: datetime

    class Config:
        from_attributes = True