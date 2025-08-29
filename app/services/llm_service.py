# app/services/llm_service.py
"""
Async-only streaming helper for google-genai (new SDK).

Behavior:
 - Uses genai.Client.models.generate_content_stream for streaming responses.
 - Calls the provided async `ws_send` for each chunk in the same event loop.
 - Provides a simple query() helper for non-streaming requests.
"""

import os
import asyncio
import logging
from typing import Optional, Callable, Awaitable, Dict, Any
from google import genai
from app.utils.config import Settings
settings = Settings()
log = logging.getLogger("voice-agent.llm_service")
log.setLevel(logging.INFO)

class LLMService:
    """
    Wrapper for non-streaming queries and streaming helper usage.
    """

    def __init__(self, api_key: Optional[str], model_name: str = "gemini-2.5-flash", timeout: int = 30):
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = int(timeout or 30)
        self.enabled = bool(api_key and genai is not None)
        self.client: Optional[genai.Client] = None

        if not genai:
            log.warning("google.genai not installed. LLMService will be disabled.")
        elif api_key is None:
            log.warning("No GEMINI API key provided. LLMService will be disabled.")
        else:
            try:
                self.client = genai.Client(api_key=api_key)
                log.info("LLMService configured for model %s", model_name)
            except Exception:
                log.exception("Failed to configure google.genai client; disabling LLMService.")
                self.enabled = False

    async def query(self, prompt: str) -> str:
        """
        Simple non-streaming query helper.
        """
        if not self.enabled or not self.client:
            return ""

        def _call():
            try:
                res = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt],
                )
                return getattr(res, "text", "") or str(res)
            except Exception:
                log.exception("LLMService.query failure")
                return ""

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            log.exception("LLMService.query unexpected error")
            return ""


def _extract_text_from_chunk(chunk) -> str:
    if chunk is None:
        return ""
    text = getattr(chunk, "text", None)
    if text:
        return text
    if isinstance(chunk, dict):
        for k in ("text", "delta", "message", "content"):
            if chunk.get(k):
                return chunk[k]
    try:
        return str(chunk) or ""
    except Exception:
        return ""


async def stream_llm_response_async(
    prompt: str,
    model: str = "gemini-2.5-flash",
    ws_send: Optional[Callable[[dict], Awaitable]] = None,
    system_instruction: Optional[str] = None,
    generation_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Async-only streaming helper. Supports both async and sync iterators.
    """
    if genai is None:
        log.error("stream_llm_response_async: google.genai not installed.")
        return ""
    api_key = api_key or settings.GEMINI_API_KEY
    if not api_key:
        log.error("stream_llm_response_async: No GEMINI_API_KEY found.")
        return ""

    try:
        client = genai.Client(api_key=api_key)

        # ✅ FIX: All configs must go inside "config"
        config: Dict[str, Any] = {}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if generation_config:
            config.update(generation_config)

        stream = client.models.generate_content_stream(
            model=model,
            contents=[prompt],
            config=config if config else None,
        )

        full_text = ""
        i = 0

        if hasattr(stream, "__aiter__"):  # async iterator
            async for chunk in stream:
                text = _extract_text_from_chunk(chunk)
                if not text:
                    continue
                full_text += text
                if ws_send:
                    try:
                        await ws_send({"type": "llm_chunk", "text": text, "i": i})
                    except Exception:
                        log.exception("ws_send failed for chunk (async)")
                i += 1
        else:  # sync generator
            for chunk in stream:
                text = _extract_text_from_chunk(chunk)
                if not text:
                    continue
                full_text += text
                if ws_send:
                    try:
                        await ws_send({"type": "llm_chunk", "text": text, "i": i})
                    except Exception:
                        log.exception("ws_send failed for chunk (sync)")
                i += 1

        if ws_send:
            try:
                await ws_send({"type": "llm_done", "text": full_text})
            except Exception:
                log.debug("Failed to send llm_done")

        return full_text
    except Exception:
        log.exception("stream_llm_response_async failure")
        return ""
