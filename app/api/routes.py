import asyncio
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.schemas import (
    UploadResponse,
    ErrorResponse,
    TranscriptionResponse,
    TTSResponse,
    LLMResponse,
)
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.llm_service import LLMService
from app.utils.config import settings
from app.utils.files import save_upload_to_tmp, save_upload_to_folder
from app.utils.logger import logger

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Instantiate services once (can be swapped/mocked in tests)
stt = STTService(api_key=settings.ASSEMBLYAI_API_KEY, timeout=settings.STT_TIMEOUT_SEC)
tts = TTSService(
    api_key=settings.MURF_API_KEY,
    endpoint=settings.MURF_TTS_ENDPOINT,
    timeout=settings.TTS_TIMEOUT_SEC,
    fallback_url="/static/fallback.mp3",
)
llm = LLMService(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL, timeout=settings.LLM_TIMEOUT_SEC)

# In-memory chat store (session_id -> list of {role, content})
chat_store: Dict[str, List[dict]] = {}

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

@router.post("/transcribe/file", response_model=TranscriptionResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        try:
            text = await stt.transcribe_file(tmp_path)
        except asyncio.TimeoutError:
            logger.error("STT timed out")
            return JSONResponse(status_code=504, content={"detail": "Transcription timed out"})
        return TranscriptionResponse(transcription=text)
    except Exception as e:
        logger.exception("/transcribe/file error")
        return JSONResponse(status_code=500, content={"detail": f"Transcription error: {str(e)}"})

@router.post("/tts/echo", response_model=TTSResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def tts_echo(file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        try:
            text = await stt.transcribe_file(tmp_path)
        except asyncio.TimeoutError:
            logger.error("STT timed out in /tts/echo")
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})

        if not text.strip():
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        try:
            audio_url = await tts.generate(text, voice_id="en-US-natalie")
        except asyncio.TimeoutError:
            logger.error("TTS timed out in /tts/echo")
            return JSONResponse(status_code=504, content={"detail": "TTS timed out"})

        return TTSResponse(audio_url=audio_url, transcription=text)
    except Exception as e:
        logger.exception("/tts/echo error")
        return JSONResponse(status_code=500, content={"detail": f"TTS Echo error: {str(e)}"})

@router.post("/llm/query", response_model=LLMResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}})
async def llm_query(file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)

        # STT
        try:
            question_text = (await stt.transcribe_file(tmp_path)).strip()
        except asyncio.TimeoutError:
            logger.error("STT timed out in /llm/query")
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})

        if not question_text:
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        # LLM
        try:
            answer_text = await llm.query(question_text)
        except asyncio.TimeoutError:
            logger.error("LLM timed out in /llm/query")
            return JSONResponse(status_code=504, content={"detail": "LLM timed out"})
        except Exception as e:
            logger.exception("LLM error in /llm/query")
            return JSONResponse(status_code=502, content={"detail": "LLM error"})

        if not answer_text:
            return JSONResponse(status_code=502, content={"detail": "No response from LLM"})

        # TTS
        try:
            audio_file = await tts.generate(answer_text, voice_id="en-US-natalie")
        except asyncio.TimeoutError:
            logger.warning("TTS timed out in /llm/query; using fallback")
            audio_file = "/static/fallback.mp3"
        except Exception:
            logger.exception("TTS error in /llm/query; using fallback")
            audio_file = "/static/fallback.mp3"

        return LLMResponse(audio_url=audio_file, transcription=question_text, llm_response=answer_text, history=[])
    except Exception as e:
        logger.exception("/llm/query fatal error")
        return JSONResponse(status_code=500, content={"detail": f"LLM Audio Query error: {str(e)}"})

@router.post("/agent/chat/{session_id}", response_model=LLMResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    try:
        tmp_path = await save_upload_to_tmp(file)
        assistant_message = "I'm having trouble connecting right now."

        # STT
        try:
            user_message = (await stt.transcribe_file(tmp_path)).strip()
        except asyncio.TimeoutError:
            logger.error("STT timed out in /agent/chat")
            user_message = ""
        except Exception:
            logger.exception("STT failed in /agent/chat")
            user_message = ""

        if not user_message:
            audio_url = await tts.generate(assistant_message)
            return LLMResponse(audio_url=audio_url, transcription="", llm_response=assistant_message, history=chat_store.get(session_id, []))

        # History
        history = chat_store.get(session_id, [])
        history.append({"role": "user", "content": user_message})
        max_len = settings.HISTORY_MAX_MESSAGES
        if len(history) > max_len:
            history = history[-max_len:]

        conversation_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])

        # LLM
        try:
            assistant_text = await llm.query(conversation_text)
            if assistant_text:
                assistant_message = assistant_text
        except asyncio.TimeoutError:
            logger.error("LLM timed out in /agent/chat")
        except Exception:
            logger.exception("LLM failed in /agent/chat")

        history.append({"role": "assistant", "content": assistant_message})
        chat_store[session_id] = history[-max_len:]

        # TTS (best effort)
        try:
            audio_url = await tts.generate(assistant_message)
        except asyncio.TimeoutError:
            logger.warning("TTS timed out in /agent/chat; using fallback")
            audio_url = "/static/fallback.mp3"
        except Exception:
            logger.exception("TTS failed in /agent/chat; using fallback")
            audio_url = "/static/fallback.mp3"

        return LLMResponse(audio_url=audio_url, transcription=user_message, llm_response=assistant_message, history=chat_store.get(session_id, []))

    except Exception as e:
        logger.exception("/agent/chat fatal error")
        fallback_msg = "I'm having trouble connecting right now."
        audio_url = "/static/fallback.mp3"
        return LLMResponse(audio_url=audio_url, transcription="", llm_response=fallback_msg, history=chat_store.get(session_id, []))