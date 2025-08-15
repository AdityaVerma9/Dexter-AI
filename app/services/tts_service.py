import asyncio
import httpx
from typing import Optional

class TTSService:
    def __init__(self, api_key: str, endpoint: str, timeout: int, fallback_url: str):
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self.fallback_url = fallback_url

    async def generate(self, text: str, voice_id: str = "en-US-natalie") -> str:
        """
        Generate a TTS audio URL using Murf. Returns the audio URL or fallback.
        """
        if not text:
            return self.fallback_url

        payload = {"text": text, "voiceId": voice_id}
        headers = {"Content-Type": "application/json", "api-key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                resp = await client.post(self.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("audioFile") or self.fallback_url
        except asyncio.TimeoutError:
            # Let caller decide; here return fallback for resilience
            return self.fallback_url
        except Exception:
            return self.fallback_url
