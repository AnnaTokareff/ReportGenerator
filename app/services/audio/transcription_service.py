"""Transcription service using OpenAI Whisper API."""
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from openai import AsyncOpenAI


class TranscriptionService:
    def __init__(self, api_key: Optional[str] = None):
        # Try to get API key from parameter, then from environment, then from settings
        if api_key:
            self.api_key = api_key
        else:
            from app.core.config import settings
            self.api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in .env file or environment variables.")
        
        # Create client with extended timeout for large file uploads
        # Default timeout is 60s, but we need more for large files
        import httpx
        timeout = httpx.Timeout(600.0, connect=30.0)  # 10 minutes total, 30s connect
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=2  # Additional retries at HTTP level
        )
        self.model = "whisper-1"
    
    async def transcribe_audio(self, audio_path: str, lang: Optional[str] = None,
                               prompt: Optional[str] = None ) -> Dict[str, Any]:
        """
        Transcribe audio file to text.
        
        Language is automatically detected by Whisper if not specified.
        Supports any language that Whisper can detect.
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
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        timeout_seconds = max(120.0, file_size_mb * 30.0)  # At least 2 min, or 30 sec per MB
        timeout_seconds = min(timeout_seconds, 600.0)  # Maximum 10 minutes
        
        print(f"Transcribing file ({file_size_mb:.2f} MB), timeout: {timeout_seconds:.0f} seconds...")
        
        last_error = None
        for attempt in range(max_retries):
            try:
                with open(file_path, "rb") as audio_file:
                    # Build request parameters
                    request_params = {
                        "model": self.model,
                        "file": audio_file,
                        "response_format": "verbose_json",
                        "timestamp_granularities": ["segment"]
                    }
                    
                    # Only add language if explicitly provided (otherwise auto-detect)
                    if lang:
                        request_params["language"] = lang
                    if prompt:
                        request_params["prompt"] = prompt
                    
                    # Make API call with timeout
                    if attempt > 0:
                        print(f"Retry attempt {attempt + 1}/{max_retries}...")
                    
                    response = await asyncio.wait_for(
                        self.client.audio.transcriptions.create(**request_params),
                        timeout=timeout_seconds
                    )
                    
                    # Success - return result
                    return {
                        "text": response.text,
                        "language": response.language,
                        "duration": response.duration,
                        "segments": self.parse_segments(response.segments) if hasattr(response, 'segments') else None
                    }
                    
            except asyncio.TimeoutError:
                last_error = "Transcription timeout: File is too large or processing takes too long. Try with a smaller file or check your internet connection."
                if attempt < max_retries - 1:
                    print(f"Timeout on attempt {attempt + 1}, retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                raise Exception(last_error)
            except Exception as e:
                error_msg = str(e)
                error_str_lower = error_msg.lower()
                last_error = e
                
                # Check if it's a retryable error
                is_retryable = (
                    "connection" in error_str_lower or
                    "timeout" in error_str_lower or
                    "network" in error_str_lower or
                    "503" in error_msg or  # Service unavailable
                    "502" in error_msg or  # Bad gateway
                    "504" in error_msg     # Gateway timeout
                )
                
                if is_retryable and attempt < max_retries - 1:
                    print(f"Connection error on attempt {attempt + 1}, retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                
                # Not retryable or last attempt - raise error
                if "unsupported_country" in error_str_lower or ("region" in error_str_lower and "not supported" in error_str_lower):
                    raise Exception(
                        "OpenAI API is not available in your region. "
                        "Please use a VPN to connect from a supported region (US, EU, etc.) or contact OpenAI support."
                    )
                elif "403" in error_msg or "forbidden" in error_str_lower:
                    if "country" in error_str_lower or "region" in error_str_lower:
                        raise Exception(
                            "OpenAI API is not available in your region. "
                            "Please use a VPN or contact OpenAI support for access."
                        )
                    else:
                        raise Exception(f"Access forbidden (403): Check your API key permissions. Details: {error_msg}")
                elif "Connection" in error_msg or "timeout" in error_str_lower:
                    raise Exception(f"Connection error after {attempt + 1} attempts: Unable to reach OpenAI API. Check your internet connection, VPN, and API key. Details: {error_msg}")
                elif "rate limit" in error_str_lower:
                    raise Exception(f"Rate limit exceeded: Too many requests. Please wait and try again. Details: {error_msg}")
                elif "invalid" in error_str_lower and "api key" in error_str_lower:
                    raise Exception(f"Invalid API key: Please check your OPENAI_API_KEY in .env file. Details: {error_msg}")
                else:
                    raise Exception(f"Transcription failed: {error_msg}")
        
        # If we get here, all retries failed
        raise Exception(f"Transcription failed after {max_retries} attempts. Last error: {str(last_error)}")
            
    
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
