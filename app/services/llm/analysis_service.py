"""
Meeting analysis service using OpenAI

Extracts structured information from meeting transcriptions:
- Summary
- Topics with relevance scores
- Decisions made
- Action items with assignees and due dates
"""

import json
import os
from typing import Any, Dict, Optional

from openai import AsyncOpenAI


class MeetingAnalysisService:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        if api_key:
            self.api_key = api_key
        else:
            from app.core.config import settings
            self.api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
    
    async def analyze_transcription(self, transcription_text: str,
                                    lang: str = "en",
                                    segments: Optional[list] = None) -> Dict[str, Any]:
        """Analyze transcription and extract summary, topics, decisions, and action items"""
        
        prompt = self._build_analysis_prompt(transcription_text, lang)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model, messages=[
                    {"role": "system", "content": self._get_system_prompt(lang)},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result_json = json.loads(response.choices[0].message.content)
            
            return {
                "summary": result_json.get("summary", ""),
                "topics": result_json.get("topics", []),
                "decisions": result_json.get("decisions", []),
                "action_items": result_json.get("action_items", [])
            }
            
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse LLM response: {str(e)}")
        except Exception as e:
            raise Exception(f"Analysis failed: {str(e)}")
    
    async def identify_speakers(self, segments: list[Dict[str, Any]], lang: str = "en") -> list[Dict[str, Any]]:
        """
        Use LLM to identify speakers from transcription segments with timestamps.
        
        Args:
            segments: List of segments with start, end, text
            lang: language 
            
        Returns:
            List of segments with speaker labels added
        """
        if not segments or len(segments) == 0:
            return segments
        
        # Format segments for LLM
        segments_text = "\n".join([
            f"[{seg.get('start', 0):.1f}s - {seg.get('end', 0):.1f}s] {seg.get('text', '')}"
            for seg in segments
        ])
        
        prompt = f"""Analyze this meeting transcription with timestamps and identify different speakers.

                    Your task: Group segments by speaker. Assign the same speaker label to segments that are clearly from the same person.

                    Rules:
                    - Use "Speaker 1", "Speaker 2", "Speaker 3", etc. as labels
                    - If you can identify names from context, use them (e.g., "Anna", "Pavel")
                    - Group consecutive segments from the same speaker
                    - Consider pauses, context, and speaking style to identify speaker changes
                    - Be consistent - same person should always get the same label
                    - Do not add new information, only from the text!
                    - If there is only one speaker in the entire transcription, assign "Speaker 1" to all segments


                    Transcription with timestamps:
                    {segments_text}

                    Return JSON object with this structure:
                    {{
                        "speakers": [
                            {{"index": 0, "speaker": "Speaker 1"}},
                            {{"index": 1, "speaker": "Speaker 1"}},
                            {{"index": 2, "speaker": "Speaker 2"}}
                        ]
                    }}
                    Index corresponds to the segment order (0 = first segment, 1 = second, etc.)."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying different speakers in meeting transcriptions. Analyze timestamps and context to group segments by speaker."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            result_json = json.loads(response.choices[0].message.content)
            
            # parse speaker assignments
            speaker_map = {}
            if "speakers" in result_json and isinstance(result_json["speakers"], list):
                for item in result_json["speakers"]:
                    idx = item.get("index")
                    speaker = item.get("speaker", "Speaker 1")
                    if idx is not None:
                        speaker_map[idx] = speaker
            
            # add speaker labels to segments
            result_segments = []
            for i, segment in enumerate(segments):
                segment_copy = segment.copy()
                segment_copy["speaker"] = speaker_map.get(i, f"Speaker {i // 5 + 1}")  
                result_segments.append(segment_copy)
            
            return result_segments
            
        except Exception as e:
            print(f"Warning: Speaker identification failed: {e}. Using fallback grouping.")
            # fallback: grouping by index
            result_segments = []
            for i, segment in enumerate(segments):
                segment_copy = segment.copy()
                segment_copy["speaker"] = f"Speaker {i // 5 + 1}"  # every 5 segments
                result_segments.append(segment_copy)
            return result_segments
    
    def _get_system_prompt(self, language: str) -> str:
        """
        Get system prompt for analysis - contains role, structure, and general rules.
        """
        lang_names = {
            "en": "English",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
        }
        
        lang_name = lang_names.get(language, language.upper())
        
        return f"""You are an expert meeting analyst. Analyze meeting transcriptions and extract structured information.

                    IMPORTANT: Always respond in {lang_name} (the same language as the transcription).

                    Return a JSON object with this structure:
                    {{
                        "summary": "A detailed summary of the meeting (2-3 paragraphs) in {lang_name}",
                        "topics": [{{"name": "Topic name in {lang_name}", "relevance_score": 0.0-1.0}}],
                        "decisions": [{{
                            "decision_text": "What was decided (in {lang_name})",
                            "context": "Additional context if available (in {lang_name})",
                            "participants": ["Name1", "Name2"] or null
                        }}],
                        "action_items": [{{
                            "task_description": "What needs to be done (in {lang_name})",
                            "assignee": "Person name or null - IMPORTANT: extract who is responsible",
                            "due_date": "YYYY-MM-DD or null",
                            "priority": "low|medium|high|urgent"
                        }}]
                    }}

                    CRITICAL: When extracting action items and decisions:
                    - Identify WHO is responsible for each task (assignee)
                    - Identify WHO participated in each decision (participants)
                    - Look for direct statements like "I will do X", "Y will handle Z", "Let's assign this to NAME"
                    - Extract names even if mentioned indirectly (e.g., "Anna will prepare the report")

                    Be precise and only extract information clearly stated in the transcription.
                    All text fields must be in {lang_name}."""
                        
    def _build_analysis_prompt(self, transcription_text: str, language: str) -> str:
        """
        Build user prompt for analysis - contains only the transcription text.
        Structure and rules are in system prompt to avoid duplication.
        """
        lang_names = {
            "en": "English",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh": "Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
        }
        
        lang_name = lang_names.get(language, language.upper())
        
        return f"""Analyze this meeting transcription and extract the required information.

                    All responses must be in {lang_name} (the same language as the transcription).

                    Transcription:
                    {transcription_text}

                    Return the analysis as JSON following the structure specified in the system prompt."""


_analysis_service: Optional[MeetingAnalysisService] = None


def get_analysis_service() -> MeetingAnalysisService:
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = MeetingAnalysisService()
    return _analysis_service
