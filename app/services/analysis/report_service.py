"""
Report generation service for meetings.

This service generates formatted reports from meeting data in Markdown format.
Supports two modes:
1. Template-based (fast, cheap, predictable)
2. LLM-generated (better quality, more natural, costs tokens)
"""
from typing import Optional
from datetime import datetime
import os

from app.models.meeting_models import Meeting
from openai import AsyncOpenAI


class ReportService:
    """
    Service for generating meeting reports.
    
    Supports both template-based and LLM-generated reports.
    """
    
    def __init__(self, use_llm: bool = False):
        """
        Initialize report service.
        
        Args:
            use_llm: If True, use LLM for report generation (better quality but costs tokens)
        """
        self.use_llm = use_llm
        if use_llm:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found for LLM report generation")
            self.client = AsyncOpenAI(api_key=api_key)
            self.model = "gpt-4o-mini"
    
    async def generate_markdown(
        self,
        meeting: Meeting,
        include_transcription: bool = True,
        include_timestamps: bool = False,
        use_llm: Optional[bool] = None
    ) -> str:
        """
        Generate Markdown report from meeting data.
        
        Args:
            meeting: Meeting object with all relationships loaded
            include_transcription: Whether to include full transcription
            include_timestamps: Whether to include timestamps in transcription
            use_llm: Override default LLM setting (None = use self.use_llm)
            
        Returns:
            Markdown formatted string
        """
        # Use provided override or default
        should_use_llm = use_llm if use_llm is not None else self.use_llm
        
        if should_use_llm:
            return await self._generate_markdown_with_llm(
                meeting, include_transcription, include_timestamps
            )
        else:
            return self._generate_markdown_template(
                meeting, include_transcription, include_timestamps
            )
    
    def _generate_markdown_template(
        self,
        meeting: Meeting,
        include_transcription: bool = True,
        include_timestamps: bool = False
    ) -> str:
        """
        Generate Markdown report using template (fast, cheap, predictable).
        
        This is the default method - it's fast, doesn't cost tokens,
        and produces consistent output.
        """
        lines = []
        
        # Header
        lines.append(f"# Meeting Report: {meeting.title}")
        lines.append("")
        lines.append(f"**Date:** {meeting.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Status:** {meeting.status.value}")
        if meeting.language:
            lines.append(f"**Language:** {meeting.language}")
        if meeting.audio_duration:
            lines.append(f"**Duration:** {meeting.audio_duration:.1f} seconds")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Summary (if transcription has summary)
        if meeting.transcription and meeting.transcription.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(meeting.transcription.summary)
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Topics
        if meeting.topics:
            lines.append("## Topics Discussed")
            lines.append("")
            for topic in meeting.topics:
                lines.append(f"- **{topic.topic_name}** (relevance: {topic.relevance_score:.2f})")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        # Decisions
        if meeting.decisions:
            lines.append("## Decisions Made")
            lines.append("")
            for i, decision in enumerate(meeting.decisions, 1):
                lines.append(f"### Decision {i}")
                lines.append(f"{decision.decision_text}")
                if decision.context:
                    lines.append(f"")
                    lines.append(f"*Context:* {decision.context}")
                if decision.participants:
                    lines.append(f"")
                    lines.append(f"*Participants:* {', '.join(decision.participants)}")
                lines.append("")
            lines.append("---")
            lines.append("")
        
        # Action Items
        if meeting.action_items:
            lines.append("## Action Items")
            lines.append("")
            for i, item in enumerate(meeting.action_items, 1):
                lines.append(f"### Action Item {i}")
                lines.append(f"**Task:** {item.task_description}")
                if item.assignee:
                    lines.append(f"**Assigned to:** {item.assignee}")
                if item.due_date:
                    lines.append(f"**Due date:** {item.due_date.strftime('%Y-%m-%d')}")
                lines.append(f"**Priority:** {item.priority.value}")
                lines.append(f"**Status:** {item.status.value}")
                lines.append("")
            lines.append("---")
            lines.append("")
        
        # Full Transcription
        if include_transcription and meeting.transcription:
            lines.append("## Full Transcription")
            lines.append("")
            
            if include_timestamps and meeting.transcription.segments:
                # Include segments with timestamps
                segments = meeting.transcription.segments
                if isinstance(segments, list):
                    for segment in segments:
                        start = segment.get("start", 0)
                        end = segment.get("end", 0)
                        text = segment.get("text", "")
                        lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
                else:
                    lines.append(meeting.transcription.full_text)
            else:
                # Just full text
                lines.append(meeting.transcription.full_text)
            
            lines.append("")
        
        return "\n".join(lines)
    
    async def _generate_markdown_with_llm(
        self,
        meeting: Meeting,
        include_transcription: bool = True,
        include_timestamps: bool = False
    ) -> str:
        """
        Generate Markdown report using LLM (better quality, more natural).
        
        This method uses GPT to create a more natural, well-structured report.
        It's slower and costs tokens, but produces better quality output.
        """
        # Build context for LLM
        context_parts = []
        
        # Meeting metadata
        context_parts.append(f"Meeting Title: {meeting.title}")
        context_parts.append(f"Date: {meeting.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if meeting.language:
            context_parts.append(f"Language: {meeting.language}")
        if meeting.audio_duration:
            context_parts.append(f"Duration: {meeting.audio_duration:.1f} seconds")
        context_parts.append("")
        
        # Summary
        if meeting.transcription and meeting.transcription.summary:
            context_parts.append(f"Summary: {meeting.transcription.summary}")
            context_parts.append("")
        
        # Topics
        if meeting.topics:
            topics_list = [f"- {t.topic_name} (relevance: {t.relevance_score:.2f})" 
                          for t in meeting.topics]
            context_parts.append("Topics Discussed:")
            context_parts.extend(topics_list)
            context_parts.append("")
        
        # Decisions
        if meeting.decisions:
            context_parts.append("Decisions Made:")
            for i, decision in enumerate(meeting.decisions, 1):
                context_parts.append(f"{i}. {decision.decision_text}")
                if decision.context:
                    context_parts.append(f"   Context: {decision.context}")
                if decision.participants:
                    context_parts.append(f"   Participants: {', '.join(decision.participants)}")
            context_parts.append("")
        
        # Action Items
        if meeting.action_items:
            context_parts.append("Action Items:")
            for i, item in enumerate(meeting.action_items, 1):
                context_parts.append(f"{i}. {item.task_description}")
                if item.assignee:
                    context_parts.append(f"   Assigned to: {item.assignee}")
                if item.due_date:
                    context_parts.append(f"   Due date: {item.due_date.strftime('%Y-%m-%d')}")
                context_parts.append(f"   Priority: {item.priority.value}, Status: {item.status.value}")
            context_parts.append("")
        
        # Transcription (if needed)
        transcription_text = ""
        if include_transcription and meeting.transcription:
            if include_timestamps and meeting.transcription.segments:
                segments = meeting.transcription.segments
                if isinstance(segments, list):
                    transcription_parts = []
                    for segment in segments:
                        start = segment.get("start", 0)
                        end = segment.get("end", 0)
                        text = segment.get("text", "")
                        transcription_parts.append(f"[{start:.1f}s - {end:.1f}s] {text}")
                    transcription_text = "\n".join(transcription_parts)
                else:
                    transcription_text = meeting.transcription.full_text
            else:
                transcription_text = meeting.transcription.full_text
        
        # Build prompt
        system_prompt = """You are an expert at creating professional meeting reports. 
Create a well-structured, clear, and professional Markdown report from the provided meeting data.
The report should be easy to read and include all important information.
Use proper Markdown formatting with headers, lists, and emphasis where appropriate."""
        
        user_prompt = f"""Create a professional meeting report in Markdown format based on the following data:

{chr(10).join(context_parts)}

"""
        
        if transcription_text:
            user_prompt += f"""Full Transcription:
{transcription_text[:5000]}"""  # Limit to avoid token limits
        
        user_prompt += """

Generate a complete Markdown report with:
1. A clear title and meeting metadata
2. Executive summary section
3. Topics discussed section
4. Decisions made section (if any)
5. Action items section (if any)
6. Full transcription section (if provided)

Make it professional, well-formatted, and easy to read."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            # Fallback to template if LLM fails
            print(f"LLM report generation failed: {e}, falling back to template")
            return self._generate_markdown_template(
                meeting, include_transcription, include_timestamps
            )


_report_service: Optional[ReportService] = None


def get_report_service() -> ReportService:
    """Get or create report service instance."""
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service


def get_report() -> ReportService:
    """Alias for get_report_service for backward compatibility."""
    return get_report_service()
