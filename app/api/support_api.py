"""
RAG-based assistant API endpoints.

A simple assistant that answers questions about meetings using semantic search
through meeting transcriptions. Uses embeddings for fast and accurate retrieval.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
import numpy as np
import pickle

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.meeting_models import Meeting, Transcription, MeetingStatus
from app.services.search.embedding_service import (
    get_embedding,
    get_embeddings,
    find_most_similar,
    chunk_text
)
from openai import AsyncOpenAI
from app.core.config import settings


router = APIRouter()


class SupportQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    meeting_ids: Optional[List[int]] = None


class SupportQueryResponse(BaseModel):
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: List[dict] = Field(default_factory=list)
    needs_human: bool = False


@router.post("/query", response_model=SupportQueryResponse)
async def query_support_agent(request: SupportQueryRequest,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),) -> SupportQueryResponse:
    
    """
    Query the RAG assistant with a question.
    
    Args:
        request: Query request with question and optional meeting filters
        current_user: Authenticated user
        db: db session
        
    Returns:
        Answer with confidence score and sources
    """
    
    meetings = await _get_user_meetings(db, current_user.id, request.meeting_ids)
    
    if not meetings:
        return SupportQueryResponse(
            answer="I don't have any completed meeting transcriptions to search through",
            confidence=0.0,
            sources=[],
        )
    
    try:
        return await _semantic_search(request.question, meetings)
    except Exception as e:
        print(f"Semantic search failed: {e}")
        return _keyword_search(request.question, meetings)


async def _get_user_meetings(
    db: AsyncSession,
    user_id: int,
    meeting_ids: Optional[List[int]] = None
) -> List[Meeting]:
    """Get user's meetings with transcriptions and cached chunks."""
    
    query = (
        select(Meeting)
        .options(
            selectinload(Meeting.transcription)
            .selectinload(Transcription.chunks)
        ).where(
            Meeting.user_id == user_id,
            Meeting.status == MeetingStatus.COMPLETED
        )
    )
    
    if meeting_ids:
        query = query.where(Meeting.id.in_(meeting_ids))
    
    result = await db.execute(query)
    meetings = result.scalars().all()
    return [m for m in meetings if m.transcription]


async def _semantic_search(question: str, meetings: List[Meeting]) -> SupportQueryResponse:
    """
    Uses cached embeddings from database if available, otherwise generates on-the-fly.
    """
    
    #  embedding for the question
    question_embedding = get_embedding(question)
    
    all_chunks = []
    all_embeddings = []
    chunk_info = []  #  metadata for each chunk
    
    for meeting in meetings:
        transcription = meeting.transcription
        
        # Use cached chunks if available
        if transcription.chunks:
            for chunk_record in transcription.chunks:
                chunk_text = chunk_record.chunk_text
                embedding = pickle.loads(chunk_record.embedding)
                
                all_chunks.append(chunk_text)
                all_embeddings.append(embedding)
                chunk_info.append({
                    'meeting': meeting,
                    'text': chunk_text,
                    'index': chunk_record.chunk_index
                })
        else:
            text = transcription.full_text
            chunks = chunk_text(text, chunk_size=500, overlap=50)            
            embeddings = get_embeddings(chunks)
            
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                all_chunks.append(chunk)
                all_embeddings.append(embedding)
                chunk_info.append({
                    'meeting': meeting,
                    'text': chunk,
                    'index': idx})
    if not all_chunks:
        return SupportQueryResponse(
            answer="I don't have any transcriptions to search through.",
            confidence=0.0,
            sources=[],
        )
    
    embeddings_array = np.array(all_embeddings)
    top_matches = find_most_similar(question_embedding, embeddings_array, top_k=5)
    
    # group matches by meeting
    meetings_data = {}
    
    for chunk_idx, similarity in top_matches:
        info = chunk_info[chunk_idx]
        meeting = info['meeting']
        meeting_id = meeting.id
        
        if meeting_id not in meetings_data:
            meetings_data[meeting_id] = {
                'meeting': meeting,
                'max_similarity': similarity,
                'chunks': []
            }
        
        meetings_data[meeting_id]['chunks'].append({'text': info['text'], 'similarity': similarity})
        
        if similarity > meetings_data[meeting_id]['max_similarity']:
            meetings_data[meeting_id]['max_similarity'] = similarity
    
    # Sort by relevance
    sorted_meetings = sorted(meetings_data.values(), key=lambda x: x['max_similarity'], reverse=True)
    
    # Check if we found anything relevant
    if not sorted_meetings or sorted_meetings[0]['max_similarity'] < 0.2:
        return SupportQueryResponse(
            answer=f"I couldn't find relevant information in your meeting transcriptions to answer: '{question}'. \
            Could you provide more context or check if the information exists in your meetings?",
            confidence=0.1,
            sources=[],
            needs_human=True
        )
    
    # most relevant meeting
    best_match = sorted_meetings[0]
    meeting = best_match['meeting']
    confidence = float(best_match['max_similarity'])
    
    # build context from top chunks
    top_chunks = sorted(
        best_match['chunks'],
        key=lambda x: x['similarity'],
        reverse=True)[:5]
    
    context = ' '.join([c['text'] for c in top_chunks
        if c['similarity'] > 0.15])
    
    answer = await _generate_answer(question, context, meeting)
    
    sources = [{
        'meeting_id': meeting.id,
        'meeting_title': meeting.title,
        'meeting_date': meeting.created_at.isoformat(),
        'relevance': best_match['max_similarity']
    }]
    
    for match in sorted_meetings[1:3]:
        if match['max_similarity'] > 0.2:
            m = match['meeting']
            sources.append({
                'meeting_id': m.id,
                'meeting_title': m.title,
                'meeting_date': m.created_at.isoformat(),
                'relevance': match['max_similarity']
            })
    
    return SupportQueryResponse(
        answer=answer,
        confidence=confidence,
        sources=sources,
        needs_human=confidence < 0.2
    )


async def _generate_answer(question: str, context: str, meeting: Meeting) -> str:
    """
    Generate answer using LLM based on retrieved context
    
    Args:
        question: User's question
        context: Retrieved relevant chunks from transcriptions
        meeting: Most relevant meeting
        
    Returns:
        Generated answer string
    """
    
    if not context:
        if meeting.transcription.summary:
            return f"From meeting '{meeting.title}':\n\n{meeting.transcription.summary}"
        else:
            return f"I found a mention in meeting '{meeting.title}', but couldn't extract details."
    
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        system_prompt = """You are a helpful assistant that answers questions about meetings based on transcriptions.

                            IMPORTANT: 
                            - Answer the question DIRECTLY and CONCISELY
                            - DO NOT quote the transcription verbatim
                            - Extract the key information and present it as a clear answer
                            - If asked "When is X?", answer with the date/time directly
                            - If asked "Who attended?", list the names directly
                            - If asked "What was decided?", summarize the decisions briefly

                            Example:
                            Question: "When is the product launch scheduled?"
                            Bad answer: "Good morning everyone, let's start our Q4 product launch planning meeting..."
                            Good answer: "The product launch is scheduled for December 20th, with a beta release to 100 users on December 19th."

                            Always provide direct answers, not quotes from the transcription."""
        
        user_prompt = f"""Question: {question}

                        Meeting context:
                        {context}

                        Answer the question directly based on the context above. Do not quote the context - extract and summarize the information."""
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        
        generated = response.choices[0].message.content.strip()
        meeting_date = meeting.created_at.strftime('%Y-%m-%d')
        
        return f"From meeting '{meeting.title}' ({meeting_date}):\n\n{generated}"
        
    except Exception as e:
        print(f"LLM generation failed: {e}")
        meeting_date = meeting.created_at.strftime('%Y-%m-%d')
        return f"From meeting '{meeting.title}' ({meeting_date}):\n\n{context}"


def _keyword_search(question: str, meetings: List[Meeting]) -> SupportQueryResponse:
    """
    Simple keyword-based search (fallback when semantic search fails).
    
    """
    
    question_lower = question.lower()
    words = set(question_lower.split())
    
    results = []
    
    for meeting in meetings:
        text = meeting.transcription.full_text.lower()
        text_words = set(text.split())
        
        # count word intersection
        common = words.intersection(text_words)
        
        if common:
            score = len(common) / len(words) if words else 0
            results.append({
                'meeting': meeting,
                'score': score
            })
    
    # sort by relevance
    results.sort(key=lambda x: x['score'], reverse=True)
    
    if not results or results[0]['score'] < 0.1:
        return SupportQueryResponse(
            answer=f"I couldn't find information for the query: '{question}'.",
            confidence=0.1,
            sources=[],
            needs_human=True
        )
    
    best = results[0]
    meeting = best['meeting']
    confidence = min(best['score'] * 2, 1.0)
    
    # extract relevant sentences
    text = meeting.transcription.full_text
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    
    relevant = [
        s for s in sentences
        if any(word in s.lower() for word in words)
    ]
    
    context = '. '.join(relevant[:3])
    
    if context:
        date = meeting.created_at.strftime('%Y-%m-%d')
        answer = f"From meeting '{meeting.title}' ({date}):\n\n{context}"
    elif meeting.transcription.summary:
        answer = f"From meeting '{meeting.title}':\n\n{meeting.transcription.summary}"
    else:
        answer = f"I found a mention in '{meeting.title}', but couldn't extract details."
        confidence *= 0.7
    
    return SupportQueryResponse(
        answer=answer,
        confidence=confidence,
        sources=[{
            'meeting_id': meeting.id,
            'meeting_title': meeting.title,
            'meeting_date': meeting.created_at.isoformat(),
            'relevance': best['score']
        }],
        needs_human=confidence < 0.3
    )


@router.get("/meetings", response_model=List[dict])
async def get_user_meetings_for_support(current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db),) -> List[dict]:
    
    """
    Get list of user's meetings available for support queries    
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
            'id': m.id,
            'title': m.title,
            'date': m.created_at.isoformat(),
            'has_transcription': m.transcription is not None
        }
        for m in meetings
        if m.transcription
    ]