"""
API endpoints for meeting management.

Endpoints:
- POST /meetings/upload - uploading audio/video file and creating a meet
- GET /meetings - list all user's meets
- GET /meetings/{id} - get user's meeting details
- GET /meetings/{id}/status - check status for processing
- DELETE /meetings/{id} - delete meeting
"""
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.meeting_models import (
    Meeting,
    MeetingStatus,
    Transcription,
    ActionItem,
    Decision,
    MeetingTopic,
)
from app.models.user import User
from app.schemas.meeting_schemas import (
    MeetingResponse,
    MeetingStatusResponse,
    MeetingUploadResponse,
    ReportGenerateRequest,
    ReportResponse,
)
from app.services.audio.transcription_service import get_transcription_service
from app.services.llm.analysis_service import get_analysis_service
from app.services.analysis.report_service import get_report
from app.utils.file_handler import save_audio_file, delete_audio_file

from app.db.session import DatabaseSessionManager
from app.core.config import settings

router = APIRouter()

async def process_meeting_transcript(meet_id: int, audio_path: str, lang: str | None = None) -> None:
    """
    Background task to process meeting: transcribe audio and analyze content.
    
    Steps:
    1. Transcribe audio to text
    2. Analyze transcription to extract topics, decisions, action items
    3. Save everything to database
    """
    session_manager = DatabaseSessionManager(settings.DATABASE_URL)
    async with session_manager.session() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meet_id))
        meet = result.scalar_one_or_none()
        
        if not meet:
            return
        
        try:
            # Check OpenAI API key before starting
            if not settings.OPENAI_API_KEY:
                raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in .env file.")
            
            # Step 1: Start transcription
            meet.status = MeetingStatus.PROCESSING
            await db.commit()
            
            # Step 2: Transcribe audio
            transcription_service = get_transcription_service()
            transcription_result = await transcription_service.transcribe_audio(
                audio_path=audio_path,
                lang=lang
            )
            
            transcription = Transcription(
                meeting_id=meet_id,
                full_text=transcription_result["text"],
                language=transcription_result["language"],
                segments=transcription_result.get("segments")
            )
            db.add(transcription)
            await db.flush()  # Get transcription ID
            
            # Step 3: Analyze transcription
            analysis_service = get_analysis_service()
            analysis_result = await analysis_service.analyze_transcription(
                transcription_text=transcription_result["text"],
                lang=transcription_result["language"]
            )
            
            # Save summary
            if analysis_result.get("summary"):
                transcription.summary = analysis_result["summary"]
            
            # Save topics
            for topic_data in analysis_result.get("topics", []):
                topic = MeetingTopic(
                    meeting_id=meet_id,
                    topic_name=topic_data.get("name", ""),
                    relevance_score=topic_data.get("relevance_score", 1.0)
                )
                db.add(topic)
            
            # Save decisions
            for decision_data in analysis_result.get("decisions", []):
                decision = Decision(
                    meeting_id=meet_id,
                    decision_text=decision_data.get("decision_text", ""),
                    context=decision_data.get("context"),
                    participants=decision_data.get("participants")
                )
                db.add(decision)
            
            # Save action items
            from app.models.meeting_models import ActionItemPriority, ActionItemStatus
            from datetime import datetime as dt
            
            for item_data in analysis_result.get("action_items", []):
                # Parse due date
                due_date = None
                if item_data.get("due_date"):
                    try:
                        due_date = dt.strptime(item_data["due_date"], "%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                
                # Parse priority
                priority_map = {
                    "low": ActionItemPriority.LOW,
                    "medium": ActionItemPriority.MEDIUM,
                    "high": ActionItemPriority.HIGH,
                    "urgent": ActionItemPriority.URGENT
                }
                priority_str = item_data.get("priority", "medium").lower()
                priority = priority_map.get(priority_str, ActionItemPriority.MEDIUM)
                
                action_item = ActionItem(
                    meeting_id=meet_id,
                    task_description=item_data.get("task_description", ""),
                    assignee=item_data.get("assignee"),
                    due_date=due_date,
                    priority=priority,
                    status=ActionItemStatus.TODO
                )
                db.add(action_item)
            
            # Step 4: Mark as completed
            meet.status = MeetingStatus.COMPLETED
            meet.language = transcription_result["language"]
            await db.commit()
            print(f"Meeting {meet_id} processing completed successfully")

        except Exception as e:
            meet.status = MeetingStatus.FAILED
            meet.error_message = str(e)
            await db.commit()
            print(f"Meeting {meet_id} processing failed: {e}")


@router.post("/upload", response_model=MeetingUploadResponse, status_code=status.HTTP_201_CREATED)

async def upload_meeting(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingUploadResponse:
    """
    Upload audio file and create meeting.
    
    Language is automatically detected by Whisper API.
    
    This endpoint:
    1. Validates and saves the audio file
    2. Creates meeting record in database
    3. Starts background transcription task (with automatic language detection)
    4. Returns immediately (doesn't wait for transcription)
    
    The user can poll GET /meetings/{id}/status to check progress.
    
    Args:
        title: meeting title
        file: audio or video file (mp3, wav, ogg, m4a, mp4, mov, avi, webm, mkv, etc.)
               Whisper API automatically extracts audio from video files
        current_user: authenticated user
        db: db session
        
    Returns:
        Meeting info with processing status
    """
    # Save audio file
    try:
        audio_path, duration, audio_format = await save_audio_file(file)
    except HTTPException:
        # Re-raise HTTP exceptions as-is (they already have proper status codes)
        raise
    except Exception as e:
        # Log the full error for debugging
        import traceback
        error_details = traceback.format_exc()
        print(f"Error saving audio file: {error_details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save audio file: {str(e)}"
        )
    
    # Create meeting record
    # Language will be detected automatically during transcription
    try:
        meeting = Meeting(
            user_id=current_user.id,
            title=title,
            audio_file_path=audio_path,
            audio_duration=duration,
            audio_format=audio_format,
            language=None,  # Will be set after transcription
            status=MeetingStatus.PENDING
        )
        
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
    except Exception as e:
        # If database operation fails, try to clean up the saved file
        import traceback
        error_details = traceback.format_exc()
        print(f"Error creating meeting record: {error_details}")
        try:
            delete_audio_file(audio_path)
        except:
            pass  # Ignore cleanup errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create meeting record: {str(e)}"
        )
    
    # Start background processing (transcription + analysis)
    # Language will be detected automatically by Whisper
    background_tasks.add_task(
        process_meeting_transcript,
        meet_id=meeting.id,
        audio_path=audio_path,
        lang=None  # Auto-detect language
    )
    
    return MeetingUploadResponse(
        id=meeting.id,
        title=meeting.title,
        status=meeting.status,
        audio_file_path=meeting.audio_file_path,
        created_at=meeting.created_at,
        message="Meeting uploaded successfully. Transcription is in progress..."
    )


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MeetingResponse]:
    """
    Get list of all user's meetings.
    
    Args:
        current_user: Authenticated user
        db: Database session
        
    Returns:
        List of user's meetings
    """
    result = await db.execute(
        select(Meeting)
        .options(
            selectinload(Meeting.transcription),
            selectinload(Meeting.topics),
            selectinload(Meeting.decisions),
            selectinload(Meeting.action_items)
        )
        .where(Meeting.user_id == current_user.id)
        .order_by(Meeting.created_at.desc())
    )
    
    meetings = result.scalars().all()
    return [MeetingResponse.model_validate(meeting) for meeting in meetings]


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingResponse:
    """
    Get meeting details with full transcription and analysis.
    
    Args:
        meeting_id: meeting ID
        current_user: Authenticated user
        db: db session
        
    Returns:
        full meeting data
    """
    result = await db.execute(select(Meeting).options(
            selectinload(Meeting.transcription),
            selectinload(Meeting.topics),
            selectinload(Meeting.decisions),
            selectinload(Meeting.action_items)
        ).where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    meeting = result.scalar_one_or_none()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    return MeetingResponse.model_validate(meeting)


@router.get("/{meeting_id}/status", response_model=MeetingStatusResponse)
async def get_meeting_status(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingStatusResponse:
    """
    Checking meet processing status.
        
    Args:
        meeting_id: Meeting ID
        current_user: Authenticated user
        db: db session
        
    Returns:
        Processing status
    """
    result = await db.execute(
        select(Meeting, Transcription)
        .outerjoin(Transcription)
        .where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    meeting, transcription = row
    
    # progress
    progress = None
    if meeting.status == MeetingStatus.PENDING:
        progress = 0
    elif meeting.status == MeetingStatus.PROCESSING:
        progress = 50
    elif meeting.status == MeetingStatus.COMPLETED:
        progress = 100
    
    return MeetingStatusResponse(
        id=meeting.id,
        status=meeting.status,
        progress_percentage=progress,
        error_message=meeting.error_message,
        transcription_ready=transcription is not None
    )
    
@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete meeting and associated data.
    
    1. Delete meeting from database 
    2. Delete audio file from disk
    
    Args:
        meeting_id: Meeting ID
        current_user: Authenticated user
        db: db session
    """
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    meeting = result.scalar_one_or_none()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Delete audio file
    audio_path = meeting.audio_file_path
    
    # Delete from database (cascades to related records)
    # In SQLAlchemy 2.0 async, use execute with delete statement
    # Defense-in-depth: verify user_id in delete statement as well
    await db.execute(
        delete(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.user_id == current_user.id
        )
    )
    await db.commit()
    
    # Delete file from disk
    try:
        delete_audio_file(audio_path)
    except Exception as e:
        # Log error but don't fail the request
        print(f"Warning: Failed to delete audio file {audio_path}: {e}")


@router.post("/{meeting_id}/report", response_model=ReportResponse)
async def generate_meeting_report(
    meeting_id: int,
    request: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    Generate meeting report in Markdown format.
    
    Args:
        meeting_id: Meeting ID
        request: Report generation options
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Markdown report content
    """
    # Get meeting with all relationships
    result = await db.execute(
        select(Meeting)
        .options(
            selectinload(Meeting.transcription),
            selectinload(Meeting.topics),
            selectinload(Meeting.decisions),
            selectinload(Meeting.action_items)
        )
        .where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    meeting = result.scalar_one_or_none()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    if meeting.status != MeetingStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting processing is not complete. Please wait for transcription to finish."
        )
    
    if not meeting.transcription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting transcription not available"
        )
    
    # Generate Markdown report
    report_service = get_report()
    markdown_content = await report_service.generate_markdown(
        meeting=meeting,
        include_transcription=request.include_transcription,
        include_timestamps=request.include_timestamps
    )
    
    return ReportResponse(
        meeting_id=meeting.id,
        content=markdown_content,
        generated_at=datetime.utcnow()
    )