from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
from dotenv import load_dotenv
import asyncio
import httpx
import assemblyai as aai
import google.generativeai as genai
from typing import List

load_dotenv()

app = FastAPI()

# Static file mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory="templates")

# CORS (optional)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# API keys and endpoints
MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_TTS_ENDPOINT = "https://api.murf.ai/v1/speech/generate"
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
aai.settings.api_key = ASSEMBLYAI_API_KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment variables")
genai.configure(api_key=GEMINI_API_KEY)

# Timeout/config (tweak as needed)
STT_TIMEOUT_SEC = 18        # max time to wait for assemblyai transcribe
LLM_TIMEOUT_SEC = 20        # max time to wait for Gemini
TTS_TIMEOUT_SEC = 25        # max time to wait for Murf
HISTORY_MAX_MESSAGES = 6    # limit history to last N messages (user+assistant messages total)

# In-memory chat store (session_id -> list of {"role","content"})
chat_store = {}

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Helper: run blocking assemblyai transcribe in threadpool
async def transcribe_file_blocking(temp_filename: str) -> str:
    def _transcribe():
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(temp_filename)
        return transcript.text if getattr(transcript, "text", None) is not None else ""
    return await asyncio.to_thread(_transcribe)

# Helper: run blocking Gemini call in threadpool
async def run_gemini_blocking(prompt: str) -> str:
    def _call():
        model = genai.GenerativeModel("gemini-2.0-flash")
        # keep this call simple; if you need a more advanced payload, build it here
        res = model.generate_content(prompt)
        # 'text' attribute may be present; handle defensively
        return res.text.strip() if getattr(res, "text", None) else ""
    return await asyncio.to_thread(_call)

# Async Murf TTS via httpx
async def murf_tts_async(text: str, voice_id: str = "en-US-natalie") -> str:
    payload = {"text": text, "voiceId": voice_id}
    headers = {"Content-Type": "application/json", "api-key": MURF_API_KEY}

    async with httpx.AsyncClient(timeout=httpx.Timeout(TTS_TIMEOUT_SEC)) as client:
        resp = await client.post(MURF_TTS_ENDPOINT, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        audio_file = data.get("audioFile")
        if not audio_file:
            raise RuntimeError("No audioFile returned by Murf")
        return audio_file

# Keep an async wrapper for fallback generator
async def generate_tts_audio(text: str):
    try:
        return await asyncio.wait_for(murf_tts_async(text, voice_id="en-US-natalie"), timeout=TTS_TIMEOUT_SEC)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[WARN] TTS failed or timed out: {e}")
        # last resort: return static fallback
        return "/static/fallback.mp3"

async def generate_fallback_audio(text: str):
    # try TTS once, but if it fails, fallback to static file
    return await generate_tts_audio(text)

# Endpoints
@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    try:
        file_path = UPLOAD_DIR / file.filename
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"filename": file.filename, "content_type": file.content_type, "size": len(content)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/transcribe/file")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            return JSONResponse(status_code=400, content={"detail": "Empty audio file"})
        temp_filename = f"/tmp/{file.filename}"
        with open(temp_filename, "wb") as f:
            f.write(file_bytes)

        # Transcribe in thread and bound by timeout
        try:
            transcript_text = await asyncio.wait_for(transcribe_file_blocking(temp_filename), timeout=STT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "Transcription timed out"})
        return {"transcription": transcript_text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Transcription error: {str(e)}"})

@app.post("/tts/echo")
async def tts_echo(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"detail": "Empty audio file"})
        temp_filename = f"/tmp/{file.filename}"
        with open(temp_filename, "wb") as f:
            f.write(file_bytes)

        # STT with timeout
        try:
            transcript_text = await asyncio.wait_for(transcribe_file_blocking(temp_filename), timeout=STT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})

        if not transcript_text.strip():
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        # TTS: convert transcription back to speech (async)
        try:
            audio_url = await asyncio.wait_for(murf_tts_async(transcript_text, voice_id="en-US-natalie"), timeout=TTS_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "TTS timed out"})
        except Exception as e:
            print(f"[WARN] Murf TTS error: {e}")
            audio_url = "/static/fallback.mp3"

        return {"audio_url": audio_url, "transcription": transcript_text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"TTS Echo error: {str(e)}"})

@app.post("/llm/query")
async def llm_query(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"detail": "Empty audio file"})
        temp_filename = f"/tmp/{file.filename}"
        with open(temp_filename, "wb") as f:
            f.write(file_bytes)

        # STT
        try:
            question_text = await asyncio.wait_for(transcribe_file_blocking(temp_filename), timeout=STT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "STT timed out"})
        question_text = question_text.strip()
        if not question_text:
            return JSONResponse(status_code=400, content={"detail": "No speech detected"})

        # LLM (Gemini) call wrapped and timed out
        try:
            answer_text = await asyncio.wait_for(run_gemini_blocking(question_text), timeout=LLM_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "LLM timed out"})
        except Exception as e:
            print(f"[WARN] LLM error: {e}")
            return JSONResponse(status_code=502, content={"detail": "LLM error"})

        if not answer_text:
            return JSONResponse(status_code=502, content={"detail": "No response from LLM"})

        # TTS
        try:
            audio_file = await asyncio.wait_for(murf_tts_async(answer_text, voice_id="en-US-natalie"), timeout=TTS_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            audio_file = "/static/fallback.mp3"
        except Exception as e:
            print(f"[WARN] Murf TTS failed: {e}")
            audio_file = "/static/fallback.mp3"

        return {"audio_url": audio_file, "transcription": question_text, "llm_response": answer_text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"LLM Audio Query error: {str(e)}"})

@app.post("/agent/chat/{session_id}")
async def agent_chat(session_id: str, file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(status_code=400, content={"detail": "Empty audio file"})
        temp_filename = f"/tmp/{file.filename}"
        with open(temp_filename, "wb") as f:
            f.write(file_bytes)

        assistant_message = "I'm having trouble connecting right now."
        user_message = ""

        # STT with timeout
        try:
            user_message = await asyncio.wait_for(transcribe_file_blocking(temp_filename), timeout=STT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            print("[ERROR] STT timed out")
        except Exception as e:
            print(f"[ERROR] STT failed: {e}")

        user_message = (user_message or "").strip()
        if not user_message:
            audio_url = await generate_fallback_audio(assistant_message)
            return {"audio_url": audio_url, "transcription": "", "llm_response": assistant_message, "history": chat_store.get(session_id, [])}

        # Maintain and truncate history
        history: List[dict] = chat_store.get(session_id, [])
        history.append({"role": "user", "content": user_message})
        # keep only the last HISTORY_MAX_MESSAGES entries
        if len(history) > HISTORY_MAX_MESSAGES:
            history = history[-HISTORY_MAX_MESSAGES:]
        # build conversation prompt
        conversation_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])

        # LLM call with timeout
        try:
            assistant_text = await asyncio.wait_for(run_gemini_blocking(conversation_text), timeout=LLM_TIMEOUT_SEC)
            if assistant_text:
                assistant_message = assistant_text
        except asyncio.TimeoutError:
            print("[ERROR] LLM timed out")
        except Exception as e:
            print(f"[ERROR] LLM failed: {e}")

        history.append({"role": "assistant", "content": assistant_message})
        # store truncated history back
        chat_store[session_id] = history[-HISTORY_MAX_MESSAGES:]

        # TTS for assistant message (best effort)
        try:
            audio_url = await asyncio.wait_for(murf_tts_async(assistant_message, voice_id="en-US-natalie"), timeout=TTS_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            print("[WARN] TTS timed out")
            audio_url = "/static/fallback.mp3"
        except Exception as e:
            print(f"[WARN] TTS failed: {e}")
            audio_url = "/static/fallback.mp3"

        return {"audio_url": audio_url, "transcription": user_message, "llm_response": assistant_message, "history": chat_store.get(session_id, [])}

    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        fallback_msg = "I'm having trouble connecting right now."
        audio_url = await generate_fallback_audio(fallback_msg)
        return {"audio_url": audio_url, "transcription": "", "llm_response": fallback_msg, "history": chat_store.get(session_id, [])}
