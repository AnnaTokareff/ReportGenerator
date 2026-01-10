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
from fastapi.responses import FileResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
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
    MeetingListResponse,
    MeetingResponse,
    MeetingStatusResponse,
    MeetingUploadResponse,
    ReportGenerateRequest,
    ReportResponse,
    ReportFormat,
)
from app.services.audio.transcription import get_transcription
from app.services.llm.analysis import get_analysis
from app.services.analysis.report import get_report
from app.utils.file_handler import save_audio_file, delete_audio_file

from app.db.session import DatabaseSessionManager
from app.core.config import settings

router = APIRouter()

async def process_meeting_transcript(meet_id: int, audio_path: str, lang: str | None) -> None:
    session_manager = DatabaseSessionManager(settings.DATABASE_URL)
    async with session_manager.session() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meet_id))
        meet = result.scalar_one_or_none()
        
        if not meet:
            return
        
        try:
            meet.status = MeetingStatus.PROCESSING
            await db.commit()
            
            result = await get_transcription().transcribe_audio(
                audio_path=audio_path,
                lang=lang
            )
            transcription = Transcription(
                meeting_id=meet_id,
                full_text=result["text"],
                language=result["language"]
            )
            db.add(transcription)

            meet.status = MeetingStatus.COMPLETED
            meet.language = result["language"]
            await db.commit()
            print(f"Meeting {meet_id} transcription completed successfully")

        except Exception as e:
            meet.status = MeetingStatus.FAILED
            meet.error_message = str(e)
            await db.commit()

@router.post("/upload", response_model=MeetingUploadResponse, status_code=status.HTTP_201_CREATED)

async def upload_meeting(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    language: str | None = Form("en", max_length=10),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingUploadResponse:
    """
    Upload audio file and create meeting.
    
    This endpoint:
    1. Validates and saves the audio file
    2. Creates meeting record in database
    3. Starts background transcription task
    4. Returns immediately (doesn't wait for transcription)
    
    The user can poll GET /meetings/{id}/status to check progress.
    
    Args:
        title: meeting title
        language: language (e.g., 'en', 'fr')
        file: format audio file (mp3, wav, ogg, etc.)
        current_user: authenticated user
        db: db session
        
    Returns:
        Meeting info with processing status
    """
    #  Save audio file
    try:
        audio_path, duration, audio_format = await save_audio_file(file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save audio file: {str(e)}"
        )
    
    # create meeting record
    meeting = Meeting(
        user_id=current_user.id,
        title=title,
        audio_file_path=audio_path,
        audio_duration=duration,
        audio_format=audio_format,
        language=language,
        status=MeetingStatus.PENDING
    )
    
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    
    # background transcription
    background_tasks.add_task(
        process_meeting_transcript,
        meeting_id=meeting.id,
        audio_file_path=audio_path,
        language=language
    )
    
    return MeetingUploadResponse(
        id=meeting.id,
        title=meeting.title,
        status=meeting.status,
        audio_file_path=meeting.audio_file_path,
        created_at=meeting.created_at,
        message="Meeting uploaded successfully. Transcription is in progress..."
    )


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
    await db.execute(delete(Meeting).where(Meeting.id == meeting_id))
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
    Generate meeting report in  Markdown format).
    
    Args:
        meeting_id: Meeting ID
        request: Report generation options
        current_user: Authenticated user
        db: Database session
        
    Returns:
         report
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
    
    # generate report based on format
    report_service = get_report()
    
    if request.format == ReportFormat.MARKDOWN:
        markdown_content = await report_service.generate_markdown(
            meeting=meeting,
            include_transcription=request.include_transcription,
            include_timestamps=request.include_timestamps
        )
        
        return ReportResponse(
            meeting_id=meeting.id,
            format=request.format,
            file_url=None,
            content=markdown_content,
            generated_at=datetime.utcnow()
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {request.format}"
        )


@router.get("/{meeting_id}/report/download")
async def download_report(
    meeting_id: int,
    path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Download generated PDF report.
    
    Args:
        meeting_id: Meeting ID
        path: Report filename
        current_user: Authenticated user
        db: Database session
        
    Returns:
        PDF file
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
    
    from pathlib import Path
    
    reports_dir = Path("reports")
    file_path = reports_dir / path
    
    # Security: ensure file is in reports directory
    if not file_path.resolve().is_relative_to(reports_dir.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=path,
        media_type="application/pdf"
    )