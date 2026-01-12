"""
Report generation service for meetings in Markdown format

Uses template-based approach for simpliness
"""
from typing import Optional
from app.models.meeting_models import Meeting


class ReportService:
    """
    Service for generating meeting reports in Markdown format    
    """
    
    def __init__(self):
        pass
    
    async def generate_markdown(self, meeting: Meeting,
        include_transcription: bool = True, include_timestamps: bool = False,) -> str:
        
        """
        Generate Markdown report for a meeting.
        
        Args:
            meeting: Meeting object with all related data
            include_transcription: Whether to include full transcription
            include_timestamps: Whether to include timestamps in transcription
            
        Returns:
            Markdown formatted report string
        """
        return self._generate_markdown_template(
            meeting, include_transcription, include_timestamps
        )
    
    def _generate_markdown_template(self, meeting: Meeting,
        include_transcription: bool = True, include_timestamps: bool = False) -> str:
        
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
        
        # action Items
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
                # Include segments with timestamps and speaker grouping
                segments = meeting.transcription.segments
                if isinstance(segments, list):
                    current_speaker = None
                    for segment in segments:
                        start = segment.get("start", 0)
                        end = segment.get("end", 0)
                        text = segment.get("text", "")
                        speaker = segment.get("speaker")  
                        
                        # Group by speaker
                        if speaker and speaker != current_speaker:
                            lines.append("")
                            lines.append(f"### {speaker}")
                            lines.append("")
                            current_speaker = speaker
                        
                        if speaker:
                            lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
                        else:
                            lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
                else:
                    lines.append(meeting.transcription.full_text)
            else:
                #  full text
                lines.append(meeting.transcription.full_text)
            
            lines.append("")
        
        return "\n".join(lines)


_report_service: Optional[ReportService] = None


def get_report_service() -> ReportService:
    global _report_service
    if _report_service is None:
        _report_service = ReportService()
    return _report_service


def get_report() -> ReportService:
    return get_report_service()
