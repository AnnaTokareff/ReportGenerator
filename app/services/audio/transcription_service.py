"""Transcription service using OpenAI Whisper API."""
import os
from pathlib import Path
from typing import Optional, Dict, Any

from openai import AsyncOpenAI


class TranscriptionService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found")
        
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = "whisper-1"
    
    async def transcribe_audio(self, audio_path: str, lang: Optional[str] = None,
                               prompt: Optional[str] = None ) -> Dict[str, Any]:
        """Transcribe audio file to text"""
        
        file_path = Path(audio_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 25:
            raise ValueError(f"File size {file_size_mb:.2f} MB exceeds 25MB limit.")
        
        try:
            with open(file_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    language=lang,
                    prompt=prompt,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            return {
                "text": response.text,
                "language": response.language,
                "duration": response.duration,
                "segments": self.parse_segments(response.segments) if hasattr(response, 'segments') else None
            }
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")
    
    def parse_segments(self, segments: Any) -> Optional[list[Dict[str, Any]]]:
        if not segments:
            return None
        
        return [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            for segment in segments
        ]


transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    global transcription_service
    if transcription_service is None:
        transcription_service = TranscriptionService()
    return transcription_service
