import asyncio
import assemblyai as aai
from typing import Optional

class STTService:
    def __init__(self, default_api_key: Optional[str], timeout: int):
        """
        Initialize with a default API key (e.g., from .env).
        """
        self.default_api_key = default_api_key
        self.timeout = timeout

    async def transcribe_file(self, filepath: str, api_key: Optional[str] = None) -> str:
        """
        Transcribe a local audio file using AssemblyAI.
        If api_key is provided, it overrides the default.
        Runs in a thread to avoid blocking.
        """
        key = api_key or self.default_api_key
        if not key:
            raise ValueError("AssemblyAI API key is required")

        def _transcribe():
            # IMPORTANT: set the key inside the thread for this call
            aai.settings.api_key = key
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(filepath)
            return getattr(transcript, "text", "") or ""

        return await asyncio.wait_for(asyncio.to_thread(_transcribe), timeout=self.timeout)
