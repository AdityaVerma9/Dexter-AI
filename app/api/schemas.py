from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class UploadResponse(BaseModel):
    filename: str
    content_type: Optional[str] = None
    size: int

class ErrorResponse(BaseModel):
    detail: str

class TranscriptionResponse(BaseModel):
    transcription: str

class TTSResponse(BaseModel):
    audio_url: str
    transcription: Optional[str] = None

class LLMResponse(BaseModel):
    audio_url: str
    transcription: str
    llm_response: str
    history: List[Dict[str, Any]] = []