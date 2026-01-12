"""
API endpoints for meeting management

Endpoints:
- POST /meetings/upload - uploading audio/video file and creating a meet
- GET /meetings - list all user's meets
- GET /meetings/{id} - get user's meeting details
- GET /meetings/{id}/status - check status for processing
- DELETE /meetings/{id} - delete meeting
"""

import traceback
from datetime import datetime, timezone

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
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import DatabaseSessionManager, get_db
from app.models.meeting_models import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    Decision,
    Meeting,
    MeetingStatus,
    MeetingTopic,
    Transcription,
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

router = APIRouter()

@router.post("/upload", response_model=MeetingUploadResponse, status_code=status.HTTP_201_CREATED)

async def upload_meeting(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingUploadResponse:
    """
    Process:
        1) Save uploaded file to disk
        2) Create Meeting record with status=PENDING
        3) Start background task for transcription
        4)s Return meeting info immediately
    
    Use GET /meetings/{id}/status to check progress of transcription
    """
    try:
        print(f"[Meeting Upload] Starting file upload: {file.filename} (user: {current_user.username})")
        audio_path, duration, audio_format = await save_audio_file(file)
        print(f"[Meeting Upload] File saved successfully: {audio_path} ({duration:.1f}s, {audio_format})")
    except HTTPException:
        raise
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Error saving audio file: {error_details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save audio file: {str(e)}"
        )
    
    try:
        now = datetime.now(timezone.utc)
        meeting = Meeting(
            user_id=current_user.id,
            title=title,
            audio_file_path=audio_path,
            audio_duration=duration,
            audio_format=audio_format,
            language=None,
            status=MeetingStatus.PENDING,
            created_at=now,
            updated_at=now
        )
        
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
        print(f"[Meeting Upload] Created meeting record: ID={meeting.id}, title='{meeting.title}', status={meeting.status}")
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Error while creating meeting record: {error_details}")
        try:
            delete_audio_file(audio_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create meeting record: {str(e)}"
        )
    
    background_tasks.add_task(
        process_meeting_transcript,
        meet_id=meeting.id,
        audio_path=audio_path,
        lang=None
    )
    print(f"[Meeting Upload] Background task started for meeting {meeting.id}")
    
    return MeetingUploadResponse(
        id=meeting.id,
        title=meeting.title,
        status=meeting.status,
        audio_file_path=meeting.audio_file_path,
        created_at=meeting.created_at,
        message="Meeting uploaded with success. Transcription is in progress..."
    )


@router.get("", response_model=list[MeetingResponse])

async def list_meetings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MeetingResponse]:
    """
    List all meetings for the current user
    
    Returns meetings with:
    - transcription
    - topics
    - decisions
    - action items
    
    Ordered by creation date
    """
    result = await db.execute(select(Meeting)
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
    
    # convert models to pydantic schemas
    return [MeetingResponse.model_validate(meeting) for meeting in meetings]


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingResponse:
    """Get meeting details with transcription and analysis."""
    try:
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
        
        # fix: sometimes saved as dict instead of list
        if meeting.decisions:
            for decision in meeting.decisions:
                if decision.participants is not None:
                    if isinstance(decision.participants, dict):
                        decision.participants = list(decision.participants.values()) if decision.participants else None
                    elif not isinstance(decision.participants, list):
                        decision.participants = None
        
        # Check segments format
        if meeting.transcription and meeting.transcription.segments is not None:
            if not isinstance(meeting.transcription.segments, (list, dict)):
                meeting.transcription.segments = None
        
        try:
            return MeetingResponse.model_validate(meeting)
        except Exception as validation_error:
            error_details = traceback.format_exc()
            print(f"Validation error for meeting {meeting_id}: {error_details}")
            print(f"Meeting data: id={meeting.id}, status={meeting.status}, has_transcription={meeting.transcription is not None}")
            if meeting.transcription:
                print(f"Transcription: language={meeting.transcription.language}, segments_type={type(meeting.transcription.segments)}")
            raise
    except HTTPException:
        raise
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Error getting meeting {meeting_id}: {error_details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get meeting details: {str(e)}"
        )


@router.get("/{meeting_id}/status", response_model=MeetingStatusResponse)
async def get_meeting_status( meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeetingStatusResponse:
    
    """Check the status of the meeting """
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
    if meeting.status == MeetingStatus.PENDING:
        progress = 0
    elif meeting.status == MeetingStatus.PROCESSING:
        progress = 50
    elif meeting.status == MeetingStatus.COMPLETED:
        progress = 100
    else:
        progress = None
    
    return MeetingStatusResponse(
        id=meeting.id,
        status=meeting.status,
        progress_percentage=progress,
        error_message=meeting.error_message,
        transcription_ready=transcription is not None
    )
    
@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: int, current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),) -> None:
    """Delete meet and all related fields"""
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    meeting = result.scalar_one_or_none()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    audio_path = meeting.audio_file_path
    
    await db.execute(
        delete(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.user_id == current_user.id
        )
    )
    await db.commit()
    
    try:
        delete_audio_file(audio_path)
    except Exception as e:
        print(f"Warning: Failed to delete audio file {audio_path}: {e}")
    
    from app.utils.file_handler import delete_report_file
    try:
        delete_report_file(meeting_id)
    except Exception as e:
        print(f"Warning: Failed to delete report file for meeting {meeting_id}: {e}")


@router.post("/{meeting_id}/report", response_model=ReportResponse)
async def generate_meeting_report(
    meeting_id: int,
    request: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """Generates meeting  report in md format"""
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
    
    report_service = get_report()
    markdown_content = await report_service.generate_markdown(
        meeting=meeting,
        include_transcription=request.include_transcription,
        include_timestamps=request.include_timestamps
    )
    
    from app.utils.file_handler import save_report_file
    try:
        report_file_path = save_report_file(meeting.id, markdown_content)
    except Exception as e:
        print(f"Warning: Failed to save report file: {e}")
        report_file_path = None
    
    return ReportResponse(
        meeting_id=meeting.id,
        content=markdown_content,
        file_path=report_file_path,
        generated_at=datetime.utcnow()
    )


@router.get("/{meeting_id}/report/download")
async def download_meeting_report(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download .md report"""
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.user_id == current_user.id)
    )
    
    meeting = result.scalar_one_or_none()
    
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    from app.utils.file_handler import REPORTS_DIR
    from pathlib import Path
    
    report_filename = f"meeting_{meeting_id}_report.md"
    report_path = REPORTS_DIR / report_filename
    
    if not report_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report file not found. Please, generate the report."
        )
    
    return FileResponse(
        path=str(report_path),
        filename=report_filename,
        media_type="text/markdown"
    )
    
async def process_meeting_transcript(meet_id: int, audio_path: str, lang: str | None = None) -> None:
    """
    Background task: transcribe audio and analyze transcription.
    
    This function runs asynchronously in the background after file upload.
    1) Transcribe audio
    2) Analyze transcription to extract topics, decisions, action items
    3) Cache embeddings for semantic search
    4) Change meeting status to COMPLETED
    """
    session_manager = DatabaseSessionManager(settings.DATABASE_URL)
    async with session_manager.session() as db:
        result = await db.execute(select(Meeting).where(Meeting.id == meet_id))
        meet = result.scalar_one_or_none()
        
        if not meet:
            print(f"[Meeting {meet_id}] Meeting not found, skipping processing")
            return
        
        #  if already processed or processing
        if meet.status == MeetingStatus.COMPLETED:
            print(f"[Meeting {meet_id}] Already completed, skipping processing")
            return
        
        if meet.status == MeetingStatus.PROCESSING:
            print(f"[Meeting {meet_id}] Already processing, skipping duplicate task")
            return
        
        if meet.status == MeetingStatus.FAILED:
            print(f"[Meeting {meet_id}] Previous attempt failed, retrying...")
        
        try:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")
            
            print(f"[Meeting {meet_id}] Starting processing pipeline...")
            meet.status = MeetingStatus.PROCESSING
            await db.commit()
            print(f"[Meeting {meet_id}] Status set to PROCESSING")
            
            print(f"[Meeting {meet_id}] Starting transcription...")
            transcription_service = get_transcription_service()
            transcription_result = await transcription_service.transcribe_audio(
                audio_path=audio_path,
                lang=lang
            )
            print(f"[Meeting {meet_id}] Transcription completed: {len(transcription_result['text'])} characters, language={transcription_result['language']}")
            
            # identify speakers using LLM if segments available
            segments = transcription_result.get("segments")
            if segments:
                analysis_service = get_analysis_service()
                try:
                    segments = await analysis_service.identify_speakers(
                        segments=segments,
                        lang=transcription_result["language"]
                    )
                    print(f"Identified speakers for meeting {meet_id}")
                except Exception as e:
                    print(f"Warning: Speaker identification failed: {e}. Using segments without speaker labels.")
                    segments = transcription_result.get("segments")
            
            now = datetime.now(timezone.utc)
            transcription = Transcription(
                meeting_id=meet_id,
                full_text=transcription_result["text"],
                language=transcription_result["language"],
                segments=segments,
                created_at=now
            )
            db.add(transcription)
            await db.flush()
            print(f"[Meeting {meet_id}] Transcription saved to database")
            
            analysis_service = get_analysis_service()
            analysis_result = await analysis_service.analyze_transcription(
                transcription_text=transcription_result["text"],
                lang=transcription_result["language"]
            )
            
            if analysis_result.get("summary"):
                transcription.summary = analysis_result["summary"]
            
            for topic_data in analysis_result.get("topics", []):
                topic = MeetingTopic(
                    meeting_id=meet_id,
                    topic_name=topic_data.get("name", ""),
                    relevance_score=topic_data.get("relevance_score", 1.0),
                    created_at=now
                )
                db.add(topic)
            
            for decision_data in analysis_result.get("decisions", []):
                decision = Decision(
                    meeting_id=meet_id,
                    decision_text=decision_data.get("decision_text", ""),
                    context=decision_data.get("context"),
                    participants=decision_data.get("participants"),
                    created_at=now
                )
                db.add(decision)
            
            for item_data in analysis_result.get("action_items", []):
                due_date = None
                if item_data.get("due_date"):
                    try:
                        due_date = datetime.strptime(item_data["due_date"], "%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
                
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
                    status=ActionItemStatus.TODO,
                    created_at=now,
                    updated_at=now
                )
                db.add(action_item)
            
            # cache embeddings before changing status to COMPLETED
            # Generate embeddings OUTSIDE of database session context to avoid greenlet issues
            chunk_records_data = []
            try:
                import pickle
                import asyncio
                
                from app.services.search.embedding_service import (
                    chunk_text,
                    get_embeddings,
                )
                
                transcription_text = transcription.full_text
                
                max_chunks = None
                if len(transcription_text) > 100_000:
                    max_chunks = 500  # Limit to 500 chunks for very long transcriptions
                    print(f"[Meeting {meet_id}] Long transcription detected ({len(transcription_text)} chars), limiting to {max_chunks} chunks")
                
                chunks = chunk_text(transcription_text, chunk_size=500, overlap=50, max_chunks=max_chunks)
                
                if chunks:
                    print(f"[Meeting {meet_id}] Generating embeddings for {len(chunks)} chunks...")
                    # Generate embeddings in thread pool - completely outside DB session context
                    chunk_embeddings = await asyncio.to_thread(get_embeddings, chunks, 100)
                    
                    # Prepare all chunk data BEFORE adding to session
                    for idx, (chunk_text_item, embedding) in enumerate(zip(chunks, chunk_embeddings)):
                        embedding_bytes = pickle.dumps(embedding)
                        chunk_records_data.append({
                            'transcription_id': transcription.id,
                            'chunk_index': idx,
                            'chunk_text': chunk_text_item,
                            'embedding': embedding_bytes,
                            'created_at': now
                        })
                    
                    print(f"[Meeting {meet_id}] Prepared {len(chunk_records_data)} chunk records")
            except Exception as e:
                print(f"[Meeting {meet_id}] Warning: Failed to generate embeddings: {e}")
                import traceback
                print(f"[Meeting {meet_id}] Embedding error details: {traceback.format_exc()}")
            
            # Now add chunks to session (only if generation was successful)
            if chunk_records_data:
                try:
                    from app.models.meeting_models import TranscriptionChunk
                    for chunk_data in chunk_records_data:
                        chunk_record = TranscriptionChunk(**chunk_data)
                        db.add(chunk_record)
                    
                    await db.flush()  # Flush chunks before final commit
                    print(f"[Meeting {meet_id}] Cached {len(chunk_records_data)} chunks")
                except Exception as e:
                    print(f"[Meeting {meet_id}] Warning: Failed to save chunks to database: {e}")
            
            # Now commit everything together: transcription, analysis results, and embeddings
            meet.status = MeetingStatus.COMPLETED
            meet.language = transcription_result["language"]
            await db.commit()
            print(f"[Meeting {meet_id}] Status set to COMPLETED")
            
            print(f"Meeting {meet_id} processing completed!")

        except Exception as e:
            try:
                await db.rollback()
                meet.status = MeetingStatus.FAILED
                meet.error_message = str(e)
                await db.commit()
                print(f"[Meeting {meet_id}] Processing failed: {e}")
            except Exception as commit_error:
                print(f"[Meeting {meet_id}] Error updating status to FAILED: {commit_error}")
                print(f"[Meeting {meet_id}] Original error: {e}")
