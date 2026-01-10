"""
Support agent API endpoints.

Support agent with semantic search that can answer questions based on meeting transcriptions.
Uses sentence-transformers for semantic search (works on CPU, no GPU needed).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
import numpy as np

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.meeting_models import Meeting, Transcription, MeetingStatus
from app.services.search.embedding_service import (
    get_embedding,
    get_embeddings,
    find_most_similar,
    chunk_text
)


router = APIRouter()


class SupportQueryRequest(BaseModel):
    """Request schema for support queries."""
    question: str = Field(..., min_length=1, max_length=1000, description="User's question")
    meeting_ids: Optional[List[int]] = Field(None, description="Specific meetings to search (optional)")


class SupportQueryResponse(BaseModel):
    """Response schema for support queries."""
    answer: str = Field(..., description="Agent's answer")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    sources: List[dict] = Field(default_factory=list, description="Meeting sources used")
    needs_human: bool = Field(False, description="Whether human support is needed")


@router.post("/query", response_model=SupportQueryResponse)
async def query_support_agent(
    request: SupportQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SupportQueryResponse:
    """
    Query the support agent with a question.
    
    The agent searches through user's meeting transcriptions to find relevant information.
    
    Args:
        request: Query request with question
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Answer with confidence score and sources
    """
    # Step 1: Get user's meetings with transcriptions
    query = select(Meeting).options(
        selectinload(Meeting.transcription)
    ).where(
        Meeting.user_id == current_user.id,
        Meeting.status == MeetingStatus.COMPLETED
    )
    
    # Filter by specific meetings if provided
    if request.meeting_ids:
        query = query.where(Meeting.id.in_(request.meeting_ids))
    
    result = await db.execute(query)
    meetings = result.scalars().all()
    
    if not meetings:
        return SupportQueryResponse(
            answer="I don't have any completed meeting transcriptions to search through. Please upload and process a meeting first.",
            confidence=0.0,
            sources=[],
            needs_human=False
        )
    
    # Step 2: Semantic search through transcriptions
    # Generate embedding for the question
    try:
        question_embedding = get_embedding(request.question)
    except Exception as e:
        # Fallback to keyword search if embeddings fail
        print(f"Embedding generation failed: {e}, falling back to keyword search")
        return _keyword_search(request.question, meetings)
    
    # Prepare all transcription chunks with their metadata
    all_chunks = []
    chunk_metadata = []  # (meeting_id, meeting_title, chunk_index, original_text)
    
    for meeting in meetings:
        if not meeting.transcription:
            continue
        
        transcription_text = meeting.transcription.full_text
        
        # Split transcription into chunks for better search
        chunks = chunk_text(transcription_text, chunk_size=500, overlap=50)
        
        for idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_metadata.append({
                "meeting": meeting,
                "chunk_index": idx,
                "chunk_text": chunk
            })
    
    if not all_chunks:
        return SupportQueryResponse(
            answer="I don't have any transcriptions to search through.",
            confidence=0.0,
            sources=[],
            needs_human=False
        )
    
    # Generate embeddings for all chunks
    try:
        chunk_embeddings = get_embeddings(all_chunks)
    except Exception as e:
        print(f"Chunk embedding generation failed: {e}, falling back to keyword search")
        return _keyword_search(request.question, meetings)
    
    # Find most similar chunks
    top_matches = find_most_similar(question_embedding, chunk_embeddings, top_k=5)
    
    # Group matches by meeting and calculate relevance
    meeting_scores = {}
    for chunk_idx, similarity in top_matches:
        metadata = chunk_metadata[chunk_idx]
        meeting = metadata["meeting"]
        
        if meeting.id not in meeting_scores:
            meeting_scores[meeting.id] = {
                "meeting": meeting,
                "max_similarity": similarity,
                "chunks": []
            }
        
        meeting_scores[meeting.id]["chunks"].append({
            "text": metadata["chunk_text"],
            "similarity": similarity
        })
        
        # Update max similarity if this chunk is more relevant
        if similarity > meeting_scores[meeting.id]["max_similarity"]:
            meeting_scores[meeting.id]["max_similarity"] = similarity
    
    # Convert to list and sort by relevance
    relevant_meetings = [
        {
            "meeting": data["meeting"],
            "relevance": data["max_similarity"],
            "chunks": data["chunks"]
        }
        for data in meeting_scores.values()
    ]
    relevant_meetings.sort(key=lambda x: x["relevance"], reverse=True)
    
    # Step 3: Generate answer from semantic search results
    if not relevant_meetings or relevant_meetings[0]["relevance"] < 0.3:
        # Low confidence - no relevant information found
        return SupportQueryResponse(
            answer=f"I couldn't find relevant information in your meeting transcriptions to answer: '{request.question}'. Could you provide more context or check if the information exists in your meetings?",
            confidence=0.1,
            sources=[],
            needs_human=relevant_meetings[0]["relevance"] < 0.2 if relevant_meetings else False
        )
    
    # Use most relevant meeting and chunks
    best_match = relevant_meetings[0]
    meeting = best_match["meeting"]
    confidence = float(best_match["relevance"])  # Already 0-1 from cosine similarity
    
    # Build answer from top matching chunks
    top_chunks = sorted(best_match["chunks"], key=lambda x: x["similarity"], reverse=True)[:3]
    context_parts = [chunk["text"] for chunk in top_chunks]
    context = " ".join(context_parts)
    
    if context:
        answer = f"Based on your meeting '{meeting.title}' ({meeting.created_at.strftime('%Y-%m-%d')}):\n\n{context}"
    else:
        # Fallback: use summary if available
        if meeting.transcription.summary:
            answer = f"Based on your meeting '{meeting.title}':\n\n{meeting.transcription.summary}"
        else:
            answer = f"I found information in your meeting '{meeting.title}', but couldn't extract a specific answer. The meeting transcription is available for review."
            confidence = confidence * 0.7  # Lower confidence
    
    # Determine if human support is needed
    needs_human = confidence < 0.3
    
    # Build sources list
    sources = [{
        "meeting_id": meeting.id,
        "meeting_title": meeting.title,
        "meeting_date": meeting.created_at.isoformat(),
        "relevance": best_match["relevance"]
    }]
    
    # Add other relevant meetings
    for match in relevant_meetings[1:3]:  # Top 2 additional sources
        if match["relevance"] > 0.3:
            sources.append({
                "meeting_id": match["meeting"].id,
                "meeting_title": match["meeting"].title,
                "meeting_date": match["meeting"].created_at.isoformat(),
                "relevance": match["relevance"]
            })
    
    return SupportQueryResponse(
        answer=answer,
        confidence=confidence,
        sources=sources,
        needs_human=needs_human
    )


def _keyword_search(question: str, meetings: List[Meeting]) -> SupportQueryResponse:
    """
    Fallback keyword-based search if semantic search fails.
    
    This is the old simple keyword matching approach.
    """
    relevant_meetings = []
    question_lower = question.lower()
    question_words = set(question_lower.split())
    
    for meeting in meetings:
        if not meeting.transcription:
            continue
        
        transcription_text = meeting.transcription.full_text.lower()
        transcription_words = set(transcription_text.split())
        
        # Calculate simple relevance score
        matching_words = question_words.intersection(transcription_words)
        if matching_words:
            relevance = len(matching_words) / len(question_words) if question_words else 0
            relevant_meetings.append({
                "meeting": meeting,
                "relevance": relevance
            })
    
    # Sort by relevance
    relevant_meetings.sort(key=lambda x: x["relevance"], reverse=True)
    
    if not relevant_meetings or relevant_meetings[0]["relevance"] < 0.1:
        return SupportQueryResponse(
            answer=f"I couldn't find relevant information to answer: '{question}'.",
            confidence=0.1,
            sources=[],
            needs_human=True
        )
    
    best_match = relevant_meetings[0]
    meeting = best_match["meeting"]
    confidence = min(best_match["relevance"] * 2, 1.0)
    
    # Extract relevant sentences
    transcription_text = meeting.transcription.full_text
    sentences = transcription_text.split('.')
    relevant_sentences = [
        s.strip() for s in sentences
        if any(word in s.lower() for word in question_words)
    ]
    
    context = '. '.join(relevant_sentences[:3])
    
    if context:
        answer = f"Based on your meeting '{meeting.title}' ({meeting.created_at.strftime('%Y-%m-%d')}):\n\n{context}"
    elif meeting.transcription.summary:
        answer = f"Based on your meeting '{meeting.title}':\n\n{meeting.transcription.summary}"
    else:
        answer = f"I found information in your meeting '{meeting.title}', but couldn't extract a specific answer."
        confidence = confidence * 0.7
    
    return SupportQueryResponse(
        answer=answer,
        confidence=confidence,
        sources=[{
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
            "meeting_date": meeting.created_at.isoformat(),
            "relevance": best_match["relevance"]
        }],
        needs_human=confidence < 0.3
    )


@router.get("/meetings", response_model=List[dict])
async def get_user_meetings_for_support(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """
    Get list of user's meetings that can be used for support queries.
    
    Returns meetings with transcriptions available.
    """
    result = await db.execute(
        select(Meeting)
        .options(selectinload(Meeting.transcription))
        .where(
            Meeting.user_id == current_user.id,
            Meeting.status == MeetingStatus.COMPLETED
        )
        .order_by(Meeting.created_at.desc())
    )
    
    meetings = result.scalars().all()
    
    return [
        {
            "id": meeting.id,
            "title": meeting.title,
            "date": meeting.created_at.isoformat(),
            "has_transcription": meeting.transcription is not None
        }
        for meeting in meetings
        if meeting.transcription
    ]
