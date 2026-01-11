"""
File handler utility for managing uploaded audio files and reports.

Responsibilities:
1. Validate uploaded files (type, size)
2. Save files to disk with unique names
3. Get audio metadata (duration, format)
4. Clean up files when needed
5. Save and manage report files
"""
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import UploadFile, HTTPException, status
from pydub import AudioSegment


UPLOAD_DIR = Path("uploads")
REPORTS_DIR = Path("reports")
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB 

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# MIME types to format mapping
ALLOWED_MIME_TYPES = {
    # Audio formats
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/m4a": "m4a",
    "audio/mp4": "mp4",
    "audio/webm": "webm",
    # Video formats (Whisper API extracts audio automatically)
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/3gpp": "3gp",
}

# File extensions to format mapping (fallback when MIME type is wrong)
ALLOWED_EXTENSIONS = {
    # Audio
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "m4a": "m4a",
    "webm": "webm",  # Can be audio or video
    # Video
    "mp4": "mp4",
    "mov": "mov",
    "avi": "avi",
    "mkv": "mkv",
    "3gp": "3gp",
}


class FileHandler:
    """
    Handles file upload, validation, and storage.
    
    Usage:
        handler = FileHandler()
        file_path, duration, format = await handler.save_audio_file(upload_file)
    """
    
    def __init__(self, upload_dir: Path = UPLOAD_DIR):
        """
        Initialize file handler.
        
        Args:
            upload_dir: Directory where files will be saved
        """
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_audio_file(
        self,
        file: UploadFile
    ) -> Tuple[str, Optional[float], str]:
        """
        Save uploaded audio or video file to disk.
        
        Supports both audio and video files. Whisper API can process video files
        directly and will extract audio automatically.
        
        Steps:
        1. Validate file type (audio or video)
        2. Validate file size
        3. Generate unique filename
        4. Save to disk
        5. Extract metadata (duration, format)
        
        Args:
            file: Uploaded file from FastAPI
            
        Returns:
            Tuple of (file_path, duration_seconds, format)
            
        Raises:
            HTTPException if validation fails
        """
        # Read file content to check size
        content = await file.read()
        await file.seek(0)  # Reset file pointer
        
        file_size = len(content)
        file_size_mb = file_size / (1024 * 1024)
        
        # Validate file size
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size {file_size_mb:.2f} MB exceeds maximum allowed size of 25 MB. "
                       f"Whisper API has a 25 MB limit. Please compress or split your file."
            )
        
        # Validate file type
        content_type = file.content_type or ""
        file_extension = None
        
        # Try to get format from MIME type
        file_format = ALLOWED_MIME_TYPES.get(content_type)
        
        # If MIME type is generic or not found, try to infer from filename
        if not file_format or content_type == "application/octet-stream":
            if file.filename:
                # Extract extension from filename
                file_extension = file.filename.rsplit('.', 1)[-1].lower()
                file_format = ALLOWED_EXTENSIONS.get(file_extension)
        
        if not file_format:
            allowed_audio = "mp3, wav, ogg, m4a, webm"
            allowed_video = "mp4, mov, avi, webm, mkv, 3gp"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type {content_type} not supported. "
                       f"Allowed audio formats: {allowed_audio}. "
                       f"Allowed video formats: {allowed_video}. "
                       f"Whisper API will extract audio from video files automatically."
            )
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}.{file_format}"
        file_path = self.upload_dir / filename
        
        # Save file to disk
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )
        
        # Extract metadata (duration)
        duration = None
        try:
            audio = AudioSegment.from_file(str(file_path))
            duration = len(audio) / 1000.0  # Convert milliseconds to seconds
        except Exception as e:
            # If metadata extraction fails, continue anyway
            # Duration is optional
            print(f"Warning: Could not extract audio duration: {e}")
        
        return str(file_path), duration, file_format
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from disk.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if deleted, False if file doesn't exist
        """
        path = Path(file_path)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
                return False
        return False


# Global instance
file_handler = FileHandler()


async def save_audio_file(file: UploadFile) -> Tuple[str, Optional[float], str]:
    """
    Convenience function to save audio file.
    
    Usage:
        from app.utils.file_handler import save_audio_file
        
        file_path, duration, format = await save_audio_file(upload_file)
    """
    return await file_handler.save_audio_file(file)


def delete_audio_file(file_path: str) -> bool:
    """Convenience function to delete audio file."""
    return file_handler.delete_file(file_path)


def save_report_file(meeting_id: int, content: str) -> str:
    """
    Save meeting report to disk.
    
    Args:
        meeting_id: Meeting ID
        content: Markdown report content
        
    Returns:
        Path to saved report file
    """
    # Ensure reports directory exists
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename: meeting_{id}_report.md
    filename = f"meeting_{meeting_id}_report.md"
    file_path = REPORTS_DIR / filename
    
    # Save content to file
    try:
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
    except Exception as e:
        raise Exception(f"Failed to save report file: {str(e)}")


def delete_report_file(meeting_id: int) -> bool:
    """
    Delete report file for a meeting.
    
    Args:
        meeting_id: Meeting ID
        
    Returns:
        True if deleted, False if file doesn't exist
    """
    filename = f"meeting_{meeting_id}_report.md"
    file_path = REPORTS_DIR / filename
    
    if file_path.exists():
        try:
            file_path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting report file {file_path}: {e}")
            return False
    return False
