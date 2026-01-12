"""Transcription service using OpenAI Whisper API."""
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from openai import AsyncOpenAI


class TranscriptionService:
    def __init__(self, api_key: Optional[str] = None):
        if api_key:
            self.api_key = api_key
        else:
            from app.core.config import settings
            self.api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set it in the .env")
        
        import httpx
        timeout = httpx.Timeout(600.0, connect=30.0)  # 10 minutes total, 30s connect
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=2  
        )
        self.model = "whisper-1"
    
    async def transcribe_audio(self, audio_path: str, lang: Optional[str] = None,
                               prompt: Optional[str] = None ) -> Dict[str, Any]:
        """
        Transcribe audio file to text
        """
        
        file_path = Path(audio_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 25:
            raise ValueError(f"File size {file_size_mb:.2f} MB exceeds 25MB limit.")
        
        # Retry logic for connection issues
        max_retries = 3
        retry_delay = 2  # seconds
        
        timeout_seconds = max(120.0, file_size_mb * 30.0)  
        timeout_seconds = min(timeout_seconds, 600.0)  # maximum 10 minutes
        
        print(f"[Transcription Service] Starting transcription: {file_size_mb:.2f} MB, timeout: {timeout_seconds:.0f} seconds...")
        
        last_error = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"[Transcription Service] Retry attempt {attempt + 1}/{max_retries} (previous attempt failed)...")
                
                with open(file_path, "rb") as audio_file:
                    request_params = {
                        "model": self.model,
                        "file": audio_file,
                        "response_format": "verbose_json",
                        "timestamp_granularities": ["segment"]
                    }
                    
                    if lang:
                        request_params["language"] = lang
                    if prompt:
                        request_params["prompt"] = prompt
                    
                    response = await asyncio.wait_for(
                        self.client.audio.transcriptions.create(**request_params),
                        timeout=timeout_seconds
                    )
                    
                    result = {
                        "text": response.text,
                        "language": response.language,
                        "duration": response.duration,
                        "segments": self.parse_segments(response.segments) if hasattr(response, 'segments') else None
                    }
                    if attempt > 0:
                        print(f"[Transcription Service] Retry successful! Transcription completed on attempt {attempt + 1}")
                    else:
                        print(f"[Transcription Service] Transcription completed successfully")
                    return result
                    
            except asyncio.TimeoutError:
                last_error = "Transcription timeout: File is too large or processing takes too long."
                if attempt < max_retries - 1:
                    print(f"[Transcription Service] Timeout on attempt {attempt + 1}/{max_retries}, retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                print(f"[Transcription Service] All retry attempts failed. Giving up.")
                raise Exception(last_error)
            except Exception as e:
                error_msg = str(e)
                error_str_lower = error_msg.lower()
                last_error = e
                
                is_retryable = (
                    "connection" in error_str_lower or
                    "timeout" in error_str_lower or
                    "network" in error_str_lower or
                    "503" in error_msg or
                    "502" in error_msg or
                    "504" in error_msg
                )
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"[Transcription Service] Connection error on attempt {attempt + 1}/{max_retries}: {error_msg[:100]}. Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  
                    continue
                
                if "invalid" in error_str_lower and "api key" in error_str_lower:
                    raise Exception(f"Invalid API key: Please check your OPENAI_API_KEY in .env file.")
                
                # for other errors, raise if last attempt, otherwise continue retry loop
                if attempt < max_retries - 1:
                    print(f"[Transcription Service] Error on attempt {attempt + 1}/{max_retries}: {error_msg[:100]}. Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                
                print(f"[Transcription Service] All {max_retries} attempts failed. Final error: {error_msg}")
                raise Exception(f"Transcription failed: {error_msg}")
            
    
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
