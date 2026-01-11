import os
import json
from typing import Optional, Dict, Any

from openai import AsyncOpenAI


class MeetingAnalysisService:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        # Try to get API key from parameter, then from settings, then from environment
        if api_key:
            self.api_key = api_key
        else:
            from app.core.config import settings
            self.api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variables.")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
    
    async def analyze_transcription(self, transcription_text: str,
                                    lang: str = "en" ) -> Dict[str, Any]:
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
    
    def _get_system_prompt(self, language: str) -> str:
        """
        Get system prompt for analysis.
        Always instructs to respond in the same language as the transcription.
        """
        # Map language codes to language names for better prompts
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

IMPORTANT: Respond in {lang_name} (the same language as the transcription).

Return a JSON object with this structure:
{{
    "summary": "A concise summary (2-3 paragraphs) in {lang_name}",
    "topics": [{{"name": "Topic name in {lang_name}", "relevance_score": 0.0-1.0}}],
    "decisions": [{{
        "decision_text": "What was decided (in {lang_name})",
        "context": "Additional context if available (in {lang_name})",
        "participants": ["Name1", "Name2"] or null
    }}],
    "action_items": [{{
        "task_description": "What needs to be done (in {lang_name})",
        "assignee": "Person name or null",
        "due_date": "YYYY-MM-DD or null",
        "priority": "low|medium|high|urgent"
    }}]
}}

Be precise and only extract information clearly stated in the transcription.
All text fields must be in {lang_name}."""
    
    def _build_analysis_prompt(self, transcription_text: str, language: str) -> str:
        """
        Build analysis prompt. Always instructs to respond in the transcription language.
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
        
        return f"""Analyze this meeting transcription and extract the following information.
All responses must be in {lang_name} (the same language as the transcription):

1. A concise summary (2-3 paragraphs) in {lang_name}
2. Main topics discussed (with relevance scores 0.0-1.0) - topic names in {lang_name}
3. Decisions made - decision text in {lang_name}
4. Action items with assignees, due dates, and priorities - task descriptions in {lang_name}

Transcription:
{transcription_text}

Return as JSON following the specified structure. Remember: all text content must be in {lang_name}."""


_analysis_service: Optional[MeetingAnalysisService] = None


def get_analysis_service() -> MeetingAnalysisService:
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = MeetingAnalysisService()
    return _analysis_service
