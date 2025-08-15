import asyncio
import assemblyai as aai
from typing import Optional

class STTService:
    def __init__(self, api_key: str, timeout: int):
        if not api_key:
            raise ValueError("AssemblyAI API key is required")
        aai.settings.api_key = api_key
        self.timeout = timeout

    async def transcribe_file(self, filepath: str) -> str:
        """
        Transcribe a local audio file using AssemblyAI in a thread to avoid blocking.
        Returns the transcribed text (empty string if nothing).
        """
        def _transcribe():
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(filepath)
            return getattr(transcript, "text", "") or ""

        return await asyncio.wait_for(asyncio.to_thread(_transcribe), timeout=self.timeout)
