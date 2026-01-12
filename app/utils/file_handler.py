"""
Responsibilities:
1. Validate uploaded files (type, size)
2. Save files to disk with unique names
3. Get audio metadata (duration, format)
4. Compress files if they exceed size limit
5. Clean up files when needed
6. Save and manage report files
"""
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import UploadFile, HTTPException, status
from pydub import AudioSegment


UPLOAD_DIR = Path("uploads")
REPORTS_DIR = Path("reports")
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (Whisper API limit)
COMPRESS_THRESHOLD = 20 * 1024 * 1024  # 20 MB -> start compressing if larger
TARGET_FILE_SIZE = 22 * 1024 * 1024  # 22 MB == target size after compression

UPLOAD_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

ALLOWED_MIME_TYPES = {
    # Audio 
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/m4a": "m4a",
    "audio/mp4": "mp4",
    "audio/webm": "webm",
    # Video 
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/3gpp": "3gp",
}

ALLOWED_EXTENSIONS = {
    # Audio
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "m4a": "m4a",
    "webm": "webm",  
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
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def _compress_audio_file(self, file_path: Path, file_format: str) -> Path:
        """
        Compress audio file using ffmpeg.
        
        Args:
            file_path: Path to original file
            file_format: File format (mp3, wav, m4a, etc.)
            
        Returns:
            Path to compressed file 
        """
        try:
            output_path = file_path.parent / f"{file_path.stem}_compressed.{file_format}"
            
            if file_format in ["mp3", "m4a"]:
                cmd = [
                    "ffmpeg", "-i", str(file_path),
                    "-b:a", "64k",  
                    "-ar", "22050", 
                    "-ac", "1",  
                    "-y", 
                    str(output_path)
                ]
            elif file_format == "wav":
                cmd = [
                    "ffmpeg", "-i", str(file_path),
                    "-b:a", "64k",
                    "-ar", "22050",
                    "-ac", "1",
                    "-y",
                    str(output_path.with_suffix(".mp3"))
                ]
                output_path = output_path.with_suffix(".mp3")
            else:
                cmd = [
                    "ffmpeg", "-i", str(file_path),
                    "-b:a", "64k",
                    "-ar", "22050",
                    "-ac", "1",
                    "-y",
                    str(output_path)
                ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0 and output_path.exists():
                compressed_size = output_path.stat().st_size
                original_size = file_path.stat().st_size
                
                if compressed_size < original_size and compressed_size <= MAX_FILE_SIZE:
                    print(f"Compressed {original_size / (1024*1024):.2f} MB -> {compressed_size / (1024*1024):.2f} MB")
                    # delete original file
                    file_path.unlink()
                    return output_path
                else:
                    if output_path.exists():
                        output_path.unlink()
                    return file_path
            else:
                # if compression failed, use original
                if output_path.exists():
                    output_path.unlink()
                return file_path
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"Warning: Compression failed: {e}. Using original file.")
            if 'output_path' in locals() and output_path.exists():
                output_path.unlink()
            return file_path
    
    def _compress_video_file(self, file_path: Path, file_format: str) -> Path:
        """
        Compress video file or extract audio using ffmpeg.
        """
        try:
            # extract audio as mp3
            output_path = file_path.parent / f"{file_path.stem}_audio.mp3"
            
            cmd = [
                "ffmpeg", "-i", str(file_path),
                "-vn",  
                "-acodec", "libmp3lame",
                "-b:a", "64k", 
                "-ar", "22050",  
                "-ac", "1",  
                "-y", 
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300
            )
            
            if result.returncode == 0 and output_path.exists():
                compressed_size = output_path.stat().st_size
                
                if compressed_size <= MAX_FILE_SIZE:
                    print(f"Extracted audio: {compressed_size / (1024*1024):.2f} MB")
                    file_path.unlink()
                    return output_path
                else:
                    if output_path.exists():
                        output_path.unlink()
                    return file_path
            else:
                if output_path.exists():
                    output_path.unlink()
                return file_path
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"Warning: Video compression failed: {e}")
            if 'output_path' in locals() and output_path.exists():
                output_path.unlink()
            return file_path
    
    async def save_audio_file(self, file: UploadFile
            ) -> Tuple[str, Optional[float], str]:
        """
        Save uploaded audio or video file to disk
        
        1. Validate file type (audio or video)
        2. Validate file size
        3. Generate unique filename
        4. Save to disk
        5. Extract metadata (duration, format)
        
        Args:
            file: file from FastAPI
            
        Returns:
             (file_path, duration_seconds, format)
            
        Raises:
            HTTPException if validation fails
        """
        content = await file.read()
        await file.seek(0)  
        
        file_size = len(content)
        file_size_mb = file_size / (1024 * 1024)
        
        content_type = file.content_type or ""
        file_extension = None        
        file_format = ALLOWED_MIME_TYPES.get(content_type)
        
        if not file_format or content_type == "application/octet-stream":
            if file.filename:
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
            )
        
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}.{file_format}"
        file_path = self.upload_dir / filename
        
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file: {str(e)}"
            )
        
        needs_compression = file_size > COMPRESS_THRESHOLD
        is_video = content_type.startswith("video/")
        is_audio = content_type.startswith("audio/")
        
        if file_size > MAX_FILE_SIZE:
            print(f"File size {file_size_mb:.2f} MB exceeds limit. Attempting to compress...")
            
            if is_video:
                file_path = self._compress_video_file(file_path, file_format)
                if file_path.suffix == ".mp3":
                    file_format = "mp3"
            elif is_audio:
                file_path = self._compress_audio_file(file_path, file_format)
                if file_path.suffix != f".{file_format}":
                    file_format = file_path.suffix[1:]  
            
            final_size = file_path.stat().st_size
            final_size_mb = final_size / (1024 * 1024)
            
            if final_size > MAX_FILE_SIZE:
                file_path.unlink()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File size {final_size_mb:.2f} MB still exceeds maximum allowed size of 25 MB "
                           f"after compression. Please split the file into smaller parts."
                )
            else:
                print(f"Successfully compressed to {final_size_mb:.2f} MB")
        
        elif needs_compression:
            print(f"File size {file_size_mb:.2f} MB is large. Needs compressing")
        
        #  metadata (duration)
        duration = None
        try:
            audio = AudioSegment.from_file(str(file_path))
            duration = len(audio) / 1000.0  #  milliseconds to seconds
        except Exception as e:
            print(f"Warning: Could not extract duration: {e}")
        return str(file_path), duration, file_format
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from disk.
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


file_handler = FileHandler()

async def save_audio_file(file: UploadFile) -> Tuple[str, Optional[float], str]:
    return await file_handler.save_audio_file(file)


def delete_audio_file(file_path: str) -> bool:
    return file_handler.delete_file(file_path)


def save_report_file(meeting_id: int, content: str) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    filename = f"meeting_{meeting_id}_report.md"
    file_path = REPORTS_DIR / filename
    
    try:
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
    except Exception as e:
        raise Exception(f"Failed to save report file: {str(e)}")


def delete_report_file(meeting_id: int) -> bool:
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
