import asyncio
import google.generativeai as genai
from typing import Optional

class LLMService:
    def __init__(self, api_key: str, model_name: str, timeout: int):
        if not api_key:
            raise ValueError("Gemini API key is required")
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.timeout = timeout

    async def query(self, prompt: str) -> str:
        """
        Synchronously call the Gemini model in a thread to avoid blocking the event loop.
        Returns the text response or empty string on failure.
        """
        def _call():
            model = genai.GenerativeModel(self.model_name)
            res = model.generate_content(prompt)
            return getattr(res, "text", "") or ""

        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=self.timeout)
