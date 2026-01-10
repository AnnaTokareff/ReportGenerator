import os
import json
from typing import Optional, Dict, Any

from openai import AsyncOpenAI


class MeetingAnalysisService:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found...")
        
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
        prompts = {
            "en": 
                
                """You are an expert meeting analyst. Analyze meeting transcriptions and extract structured information.

                    Return a JSON object with this structure:
                    {
                        "summary": "A concise summary (2-3 paragraphs)",
                        "topics": [{"name": "Topic name", "relevance_score": 0.0-1.0}],
                        "decisions": [{
                            "decision_text": "What was decided",
                            "context": "Additional context if available",
                            "participants": ["Name1", "Name2"] or null
                        }],
                        "action_items": [{
                            "task_description": "What needs to be done",
                            "assignee": "Person name or null",
                            "due_date": "YYYY-MM-DD or null",
                            "priority": "low|medium|high|urgent"
                        }]
                    }

                    Be precise and only extract information clearly stated in the transcription.""",
                    
                    
            "fr": 
                
                """Vous êtes un expert en analyse de réunions. Analysez les transcriptions et extrayez des informations structurées.

                    Retournez un objet JSON avec cette structure:
                    {
                        "summary": "Un résumé concis (2-3 paragraphes)",
                        "topics": [{"name": "Nom du sujet", "relevance_score": 0.0-1.0}],
                        "decisions": [{
                            "decision_text": "Ce qui a été décidé",
                            "context": "Contexte supplémentaire si disponible",
                            "participants": ["Nom1", "Nom2"] ou null
                        }],
                        "action_items": [{
                            "task_description": "Ce qui doit être fait",
                            "assignee": "Nom de la personne ou null",
                            "due_date": "YYYY-MM-DD ou null",
                            "priority": "low|medium|high|urgent"
                        }]
                    }

                    Soyez précis et n'extrayez que les informations clairement énoncées."""
        }
        return prompts.get(language, prompts["en"])
    
    def _build_analysis_prompt(self, transcription_text: str, language: str) -> str:
        prompts = {
            "en": 
                f"""Analyze this meeting transcription and extract:
                    1. A concise summary (2-3 paragraphs)
                    2. Main topics discussed (with relevance scores 0.0-1.0)
                    3. Decisions made
                    4. Action items with assignees, due dates, and priorities

                    Transcription:
                    {transcription_text}

                    Return as JSON following the specified structure.""",
                                "fr": f"""Analysez cette transcription de réunion et extrayez:
                    1. Un résumé concis (2-3 paragraphes)
                    2. Les principaux sujets discutés (avec scores 0.0-1.0)
                    3. Les décisions prises
                    4. Les éléments d'action avec assignés, dates et priorités

                    Transcription:
                    {transcription_text}

                Retournez en JSON suivant la structure spécifiée."""
        }
        return prompts.get(language, prompts["en"])


_analysis_service: Optional[MeetingAnalysisService] = None


def get_analysis_service() -> MeetingAnalysisService:
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = MeetingAnalysisService()
    return _analysis_service
