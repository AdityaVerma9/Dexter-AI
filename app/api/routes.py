
import asyncio
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, UploadFile, File, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.api.schemas import (
    UploadResponse,
    ErrorResponse,
    TranscriptionResponse,
    TTSResponse,
    LLMResponse,
)
from app.state import SESSION_KEYS
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.llm_service import LLMService
from app.services import weather_service 
from app.services.news_service import get_top_headlines
from app.utils.config import settings
from app.utils.files import save_upload_to_tmp, save_upload_to_folder
from app.utils.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Service instances with default API keys
# ---------------------------------------------------------------------------
stt_service = STTService(default_api_key=settings.ASSEMBLYAI_API_KEY, timeout=settings.STT_TIMEOUT_SEC)
tts_service = TTSService(
    api_key=settings.MURF_API_KEY,
    endpoint=settings.MURF_TTS_ENDPOINT,
    timeout=settings.TTS_TIMEOUT_SEC,
    fallback_url="/static/fallback.mp3",
)
llm_service = LLMService(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL, timeout=settings.LLM_TIMEOUT_SEC)

# In-memory chat store (session_id -> list of {role, content})
chat_store: Dict[str, List[dict]] = {}

# ---------------------------------------------------------------------------
# Utility functions to get API keys with proper fallback
# ---------------------------------------------------------------------------
def get_session_api_key(session_id: str, key_name: str, default_key: str = None) -> str:
    """
    Get API key with proper fallback order:
    1. Session-specific key from SESSION_KEYS
    2. Default key from environment
    3. None
    """
    if session_id and session_id in SESSION_KEYS:
        session_key = SESSION_KEYS[session_id].get(key_name)
        if session_key:
            return session_key
    return default_key

# ---------------------------------------------------------------------------
# Chat history helpers
# ---------------------------------------------------------------------------
def save_message(session_id: str, role: str, content: str):
    """Save a message to in-memory history and trim to HISTORY_MAX_MESSAGES."""
    if not session_id:
        session_id = "anon"
    history = chat_store.setdefault(session_id, [])
    history.append({"role": role, "content": content})

    max_len = getattr(settings, "HISTORY_MAX_MESSAGES", 50)
    if len(history) > max_len:
        chat_store[session_id] = history[-max_len:]
    return chat_store[session_id]

def get_history(session_id: str) -> List[dict]:
    return chat_store.get(session_id, [])

def build_conversation_text(session_id: str) -> str:
    history = get_history(session_id)
    return "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])

# ---------------------------------------------------------------------------
# Active endpoints with improved API key handling
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    logger.info("Serving index.html")
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/upload", response_model=UploadResponse, responses={500: {"model": ErrorResponse}})
async def upload_audio(file: UploadFile = File(...)):
    try:
        saved = await save_upload_to_folder(file, Path("uploads"))
        logger.info(f"Uploaded file saved to {saved['path']}")
        return UploadResponse(filename=saved["filename"], content_type=saved["content_type"], size=saved["size"])
    except Exception as e:
        logger.exception("/upload failed")
        return JSONResponse(status_code=500, content={"detail": str(e)})

@router.post("/transcribe/file", response_model=TranscriptionResponse,
             responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def transcribe_audio(request: Request, file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)

        # Get session ID and corresponding API key
        session_id = request.query_params.get("session")
        aai_key = get_session_api_key(session_id, "AAI", settings.ASSEMBLYAI_API_KEY)
        
        if not aai_key:
            return JSONResponse(status_code=400, content={"detail": "AssemblyAI API key not configured"})

        try:
            text = await stt_service.transcribe_file(tmp_path, api_key=aai_key)
        except asyncio.TimeoutError:
            logger.error("STT timed out")
            return JSONResponse(status_code=504, content={"detail": "Transcription timed out"})

        return TranscriptionResponse(transcription=text)
    except Exception as e:
        logger.exception("/transcribe/file error")
        return JSONResponse(status_code=500, content={"detail": f"Transcription error: {str(e)}"})

@router.get("/history/{session_id}")
async def http_get_history(session_id: str):
    """Return the in-memory chat history for a session."""
    return {"session_id": session_id, "history": get_history(session_id)}

@router.get("/api/weather")
async def api_weather(city: str = Query("New York"), session: str = Query(None)):
    """Fetch current weather using WeatherAPI with session-specific keys"""
    try:
        weather_key = get_session_api_key(session, "WEATHER", settings.WEATHER_API_KEY)
        
        weather = await weather_service.get_weather(
            city, 
            api_key=weather_key, 
            session_id=session
        )
        
        if weather and "error" not in weather:
            return {"ok": True, "weather": weather, "error": None}
        
        error_msg = weather.get("error") if weather else "Weather service unavailable"
        return {"ok": False, "weather": None, "error": error_msg}
        
    except Exception as e:
        logger.exception(f"Weather API error: {e}")
        return JSONResponse(
            status_code=500, 
            content={"ok": False, "weather": None, "error": f"Weather service error: {str(e)}"}
        )

@router.get("/api/news")
async def api_news(country: str = "us", category: str = None, session: str = Query(None)):
    """Fetch news headlines using NewsAPI with session-specific keys"""
    try:
        news_key = get_session_api_key(session, "NEWS", settings.NEWSAPI_KEY)
        
        articles = await get_top_headlines(
            country=country, 
            category=category, 
            page_size=5,
            api_key=news_key,
            session_id=session
        )
        
        if articles:
            return {"ok": True, "news": articles, "error": None}
        
        return {"ok": False, "news": None, "error": "Failed to fetch news - check API key configuration"}
        
    except Exception as e:
        logger.exception(f"News API error: {e}")
        return JSONResponse(
            status_code=500, 
            content={"ok": False, "news": None, "error": f"News service error: {str(e)}"}
        )

# ---------------------------------------------------------------------------
# Legacy endpoints (preserved for backward compatibility)
# ---------------------------------------------------------------------------
@router.post("/legacy/tts/echo", response_model=TTSResponse,
             responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def legacy_tts_echo(request: Request, file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        session_id = request.query_params.get("session")
        aai_key = get_session_api_key(session_id, "AAI", settings.ASSEMBLYAI_API_KEY)
        
        try:
            text = await stt_service.transcribe_file(tmp_path, api_key=aai_key)
        except asyncio.TimeoutError:
            logger.error("STT timed out in /legacy/tts/echo")
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})

        if not text.strip():
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        try:
            audio_url = await tts_service.generate(text, voice_id="en-US-natalie")
        except asyncio.TimeoutError:
            logger.error("TTS timed out in /legacy/tts/echo")
            return JSONResponse(status_code=504, content={"detail": "TTS timed out"})

        return TTSResponse(audio_url=audio_url, transcription=text)
    except Exception as e:
        logger.exception("/legacy/tts/echo error")
        return JSONResponse(status_code=500, content={"detail": f"TTS Echo error: {str(e)}"})

@router.post("/legacy/llm/query", response_model=LLMResponse,
             responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def legacy_llm_query(request: Request, file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        session_id = request.query_params.get("session")
        
        # Get session-specific keys
        aai_key = get_session_api_key(session_id, "AAI", settings.ASSEMBLYAI_API_KEY)
        gemini_key = get_session_api_key(session_id, "GEMINI", settings.GEMINI_API_KEY)
        
        try:
            question_text = (await stt_service.transcribe_file(tmp_path, api_key=aai_key)).strip()
        except asyncio.TimeoutError:
            logger.error("STT timed out in /legacy/llm/query")
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})

        if not question_text:
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        # Use session-specific LLM service
        session_llm = LLMService(api_key=gemini_key, model_name=settings.GEMINI_MODEL, timeout=settings.LLM_TIMEOUT_SEC)
        
        try:
            answer_text = await session_llm.query(question_text)
        except asyncio.TimeoutError:
            logger.error("LLM timed out in /legacy/llm/query")
            return JSONResponse(status_code=504, content={"detail": "LLM timed out"})
        except Exception:
            logger.exception("LLM error in /legacy/llm/query")
            return JSONResponse(status_code=502, content={"detail": "LLM error"})

        if not answer_text:
            return JSONResponse(status_code=502, content={"detail": "No response from LLM"})

        try:
            audio_file = await tts_service.generate(answer_text, voice_id="en-US-natalie")
        except asyncio.TimeoutError:
            logger.warning("TTS timed out in /legacy/llm/query; using fallback")
            audio_file = "/static/fallback.mp3"
        except Exception:
            logger.exception("TTS error in /legacy/llm/query; using fallback")
            audio_file = "/static/fallback.mp3"

        return LLMResponse(audio_url=audio_file, transcription=question_text, llm_response=answer_text, history=[])
    except Exception as e:
        logger.exception("/legacy/llm/query fatal error")
        return JSONResponse(status_code=500, content={"detail": f"LLM Audio Query error: {str(e)}"})

@router.post("/legacy/agent/chat/{session_id}", response_model=LLMResponse,
             responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def legacy_agent_chat(session_id: str, request: Request, file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        assistant_message = "I'm having trouble connecting right now."
        
        # Get session-specific keys
        aai_key = get_session_api_key(session_id, "AAI", settings.ASSEMBLYAI_API_KEY)
        gemini_key = get_session_api_key(session_id, "GEMINI", settings.GEMINI_API_KEY)

        try:
            user_message = (await stt_service.transcribe_file(tmp_path, api_key=aai_key)).strip()
        except asyncio.TimeoutError:
            user_message = ""
        except Exception:
            user_message = ""

        if not user_message:
            audio_url = await tts_service.generate(assistant_message)
            return LLMResponse(
                audio_url=audio_url,
                transcription="",
                llm_response=assistant_message,
                history=get_history(session_id),
            )

        save_message(session_id, "user", user_message)
        conversation_text = build_conversation_text(session_id)

        # Use session-specific LLM service
        session_llm = LLMService(api_key=gemini_key, model_name=settings.GEMINI_MODEL, timeout=settings.LLM_TIMEOUT_SEC)

        try:
            answer_text = await session_llm.query(conversation_text)
            if answer_text:
                assistant_message = answer_text
        except Exception:
            pass

        save_message(session_id, "assistant", assistant_message)

        try:
            audio_url = await tts_service.generate(assistant_message)
        except Exception:
            audio_url = "/static/fallback.mp3"

        return LLMResponse(
            audio_url=audio_url,
            transcription=user_message,
            llm_response=assistant_message,
            history=get_history(session_id),
        )

    except Exception:
        audio_url = "/static/fallback.mp3"
        return LLMResponse(
            audio_url=audio_url,
            transcription="",
            llm_response="I'm having trouble connecting right now.",
            history=get_history(session_id),
        )