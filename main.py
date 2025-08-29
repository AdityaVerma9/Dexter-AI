
import os
import time
import json
import logging
import threading
import queue
from pathlib import Path
import asyncio
import websockets

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
load_dotenv()

from app.state import SESSION_KEYS
from app.services import weather_service, news_service
from app.services.llm_service import stream_llm_response_async
from app.api.routes import router
from app.utils.config import Settings
settings = Settings()

from assemblyai.streaming.v3 import (
    StreamingClient, StreamingClientOptions, StreamingEvents,
    StreamingParameters
)

# ---------------------- Config ----------------------
AAI_API_KEY = settings.ASSEMBLYAI_API_KEY
GEMINI_API_KEY = settings.GEMINI_API_KEY
MURF_API_KEY = settings.MURF_API_KEY
WS_URL = "wss://api.murf.ai/v1/speech/stream-input"
STATIC_CONTEXT_ID = "Voiceai-context-123"
AUTO_ASSISTANT_REPLY = os.getenv("AUTO_ASSISTANT_REPLY", "true").lower() in ("1", "true", "yes")
NEWSAPI_KEY = settings.NEWSAPI_KEY
WEATHER_API_KEY = settings.WEATHER_API_KEY

# Logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("Voiceai")

# Paths
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"

# ---------------------- FastAPI Setup ----------------------
app = FastAPI(title="Voice Agent")
app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Realtime streaming server</h1>")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "assemblyai": bool(AAI_API_KEY),
            "gemini": bool(GEMINI_API_KEY),
            "murf": bool(MURF_API_KEY),
            "news": bool(NEWSAPI_KEY),
            "weather": bool(WEATHER_API_KEY)
        }
    }

# Global stores
CHAT_HISTORY: dict[str, list[dict[str, str]]] = {}
SESSION_PERSONA: dict[str, str] = {}

# Single persona (Dexter Morgan)
DEXTER_PERSONA = (
    "You are Dexter Morgan, a forensic blood spatter analyst who moonlights as a vigilante "
    "serial killer. You narrate your thoughts with cold precision, clinical detachment, and "
    "dark humor. Speak with calm, methodical tone, and often reflect on the 'dark passenger' "
    "within you. Respond thoughtfully, analyzing situations as if dissecting evidence. "
    "You may use metaphors about blood, crime scenes, or predators. "
    "Stay in character and never reveal you are an AI model. "
    "If asked to perform illegal or harmful actions, refuse but in-character, e.g., "
    "'Even my dark passenger knows some lines must never be crossed.'"
)
PERSONAS = {"default": DEXTER_PERSONA}

# ---------------------- Queue-based Audio Streamer ----------------------
class QueueAudioStreamer:
    def __init__(self, client: StreamingClient, max_queue_bytes: int = 10 * 1024 * 1024):
        self.client = client
        self.q: "queue.Queue[bytes | None]" = queue.Queue()
        self.stop_evt = threading.Event()
        self.thread: threading.Thread | None = None
        self._budget = max_queue_bytes
        self._inflight = 0

    def _gen(self):
        while not self.stop_evt.is_set():
            chunk = self.q.get()
            if chunk is None:
                break
            self._inflight -= len(chunk)
            yield chunk

    def start(self):
        def _run():
            try:
                self.client.stream(self._gen())
            except Exception as e:
                logging.exception("client.stream failed: %s", e)
        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()

    def send(self, chunk: bytes):
        sz = len(chunk)
        if self._inflight + sz > self._budget:
            return
        self._inflight += sz
        self.q.put(chunk)

    def stop(self):
        self.stop_evt.set()
        try:
            self.q.put(None)
        except Exception:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

# ---------------------- TTS Integration ----------------------
async def stream_to_murf(text_stream, ws_callback=None, api_key: str | None = None):
    key = api_key or MURF_API_KEY
    if not key:
        if ws_callback:
            await ws_callback({"type": "audio_error", "message": "No Murf API key available"})
        return

    uri = f"{WS_URL}?api-key={key}&sample_rate=44100&channel_type=MONO&format=WAV&context_id={STATIC_CONTEXT_ID}"
    
    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            voice_config = {
                "voice_config": {
                    "voiceId": "en-US-miles",
                    "style": "Calm",   
                    "rate": -0.15,             
                    "pitch": 0,            
                    "variation": 0.2 
                }
            }
            await asyncio.wait_for(ws.send(json.dumps(voice_config)), timeout=5.0)

            chunk_count = 0
            audio_chunks = []

            if ws_callback:
                await ws_callback({
                    "type": "audio_start", 
                    "context_id": STATIC_CONTEXT_ID,
                    "message": "Starting audio generation..."
                })

            async for chunk in text_stream:
                if chunk and chunk.strip():
                    chunk_count += 1
                    text_chunk = chunk.strip()
                    
                    try:
                        await asyncio.wait_for(ws.send(json.dumps({"text": text_chunk})), timeout=5.0)

                        while True:
                            try:
                                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                                data = json.loads(response)

                                if "audio" in data and data["audio"]:
                                    audio_b64 = data["audio"]
                                    audio_chunks.append(audio_b64)

                                    if ws_callback:
                                        await ws_callback({
                                            "type": "audio_chunk", 
                                            "audio": audio_b64,
                                            "format": "wav_base64",
                                            "chunk_number": len(audio_chunks),
                                            "total_chunks_so_far": len(audio_chunks),
                                            "is_final": data.get("final", False)
                                        })

                                if data.get("final"):
                                    break
                            except asyncio.TimeoutError:
                                break
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        continue

            if chunk_count > 0:
                try:
                    await asyncio.wait_for(ws.send(json.dumps({"end": True})), timeout=5.0)
                    if ws_callback:
                        await ws_callback({
                            "type": "audio_complete",
                            "total_chunks": len(audio_chunks),
                            "all_audio_chunks": audio_chunks,
                            "context_id": STATIC_CONTEXT_ID,
                            "message": f"Audio generation complete with {len(audio_chunks)} chunks"
                        })
                except Exception:
                    pass
            
    except Exception as e:
        log.error(f"Murf TTS error: {e}")
        if ws_callback:
            await ws_callback({"type": "audio_error", "message": f"Audio generation failed: {str(e)}"})

# ---------------------- LLM + TTS Handler ----------------------
async def process_transcript(session_id: str, text: str, ws_callback=None):
    keys = SESSION_KEYS.get(session_id, {})
    try:
        history = CHAT_HISTORY.setdefault(session_id, [])
        history.append({"role": "user", "content": text})

        lower_text = text.lower()

        # ---------------------- WEATHER INTENT ----------------------
        if "weather" in lower_text or "temperature" in lower_text or "forecast" in lower_text:
            city = None
            if " in " in lower_text:
                try:
                    city = lower_text.split(" in ", 1)[1].strip().split("?")[0].split(" for ")[0]
                except Exception:
                    city = None
            if not city:
                city = "New York"

            weather = await weather_service.get_weather(
                city, 
                api_key=keys.get("WEATHER"), 
                session_id=session_id
            )

            if weather and "error" not in weather:
                reply_text = (
                    f"Current weather in {weather['location']}, {weather['country']}: "
                    f"{weather['condition']}. Temperature {weather['temperature_c']}°C."
                )
            else:
                error_msg = weather.get("error", "Unknown weather error") if weather else "Weather service unavailable"
                reply_text = f"Sorry, I couldn't fetch the weather: {error_msg}"

            if ws_callback:
                await ws_callback({"type": "weather", "data": weather, "text": reply_text})

            # Use session-specific Murf key
            murf_key = keys.get("MURF")
            if murf_key:
                async def tgen(): 
                    yield reply_text
                await stream_to_murf(tgen(), ws_callback, api_key=murf_key)

            history.append({"role": "assistant", "content": reply_text})
            return

        # ---------------------- NEWS INTENT ----------------------
        if "news" in lower_text or "headlines" in lower_text or "latest" in lower_text:
            country = "us"
            articles = await news_service.get_top_headlines(
                country=country, 
                page_size=5, 
                api_key=keys.get("NEWS"),
                session_id=session_id
            )

            if articles:
                short = "Here are the top headlines:\n" + "\n".join([f"- {a['title']} ({a['source']})" for a in articles])
            else:
                short = "I couldn't fetch headlines right now. Check if your News API key is configured."

            if ws_callback:
                await ws_callback({"type": "news", "data": articles, "text": short})

            murf_key = keys.get("MURF")
            if murf_key:
                async def tgen(): 
                    yield short
                await stream_to_murf(tgen(), ws_callback, api_key=murf_key)

            history.append({"role": "assistant", "content": short})
            return

        # ---------------------- FALLBACK TO LLM ----------------------
        persona_prompt = SESSION_PERSONA.get(session_id, PERSONAS["default"])

        conversation_prompt = ""
        for turn in history:
            speaker = "User" if turn["role"] == "user" else "Assistant"
            conversation_prompt += f"{speaker}: {turn['content']}\n"
        conversation_prompt += "Assistant:"

        # Use session-specific Gemini key
        gemini_key = keys.get("GEMINI")
        
        llm_response = stream_llm_response_async(
            conversation_prompt,
            model="gemini-2.5-flash",
            system_instruction=persona_prompt,
            api_key=gemini_key
        )

        if hasattr(llm_response, '__aiter__'):
            async def text_generator():
                collected = ""
                async for chunk in llm_response:
                    if chunk:
                        collected += chunk
                        if ws_callback:
                            await ws_callback({"type": "llm_chunk", "text": chunk})
                        yield chunk
                if collected:
                    history.append({"role": "assistant", "content": collected})

            murf_key = keys.get("MURF")
            if murf_key:
                await stream_to_murf(text_generator(), ws_callback, api_key=murf_key)
            else:
                async for chunk in text_generator():
                    print(f"🤖 {chunk}", end="", flush=True)
                print()
        else:
            full_response = await llm_response
            if ws_callback:
                await ws_callback({"type": "llm_response", "text": full_response})
            if full_response:
                history.append({"role": "assistant", "content": full_response})
                
            murf_key = keys.get("MURF")
            if murf_key and full_response:
                async def single_text_gen():
                    yield full_response
                await stream_to_murf(single_text_gen(), ws_callback, api_key=murf_key)

    except Exception as e:
        log.exception(f"[LLM Error] {e}")
        if ws_callback:
            await ws_callback({"type": "error", "message": f"Processing error: {str(e)}"})

# ---------------------- WebSocket Endpoint ----------------------
@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session", f"anon-{int(time.time())}")

    # Always set default persona
    SESSION_PERSONA[session_id] = PERSONAS["default"]
    log.info(f"🎙️ Client: {session_id} | Persona: default (Dexter Morgan)")

    aai_key = websocket.query_params.get("aai") or AAI_API_KEY
    gemini_key = websocket.query_params.get("gemini") or GEMINI_API_KEY
    murf_key = websocket.query_params.get("murf") or MURF_API_KEY
    news_key = websocket.query_params.get("news") or NEWSAPI_KEY
    weather_key = websocket.query_params.get("weather") or WEATHER_API_KEY

    # Store keys for this session
    SESSION_KEYS[session_id] = {
        "AAI": aai_key, 
        "GEMINI": gemini_key, 
        "MURF": murf_key,
        "NEWS": news_key, 
        "WEATHER": weather_key
    }

    log.info(f"🔑 Session {session_id} API keys: {list(k for k, v in SESSION_KEYS[session_id].items() if v)}")

    if not aai_key:
        await websocket.send_text(json.dumps({
            "type": "error", 
            "message": "Missing AssemblyAI API key. Please configure it in settings."
        }))
        await websocket.close()
        return

    loop = asyncio.get_running_loop()
    
    async def ws_send(payload: dict):
        try:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.send_text(json.dumps(payload))
        except Exception:
            pass
            
    def sync_ws_send(payload: dict):
        asyncio.run_coroutine_threadsafe(ws_send(payload), loop)

    seen_texts = set()
    
    # Use session-specific AssemblyAI key
    client = StreamingClient(StreamingClientOptions(api_key=aai_key))

    # AssemblyAI events
    def on_begin(client, event):
        sync_ws_send({"type": "info", "message": "AssemblyAI session started"})
        
    def on_turn(client, event):
        if not event.end_of_turn or not getattr(event, "turn_is_formatted", False):
            return
        text = event.transcript.strip()
        if not text or text in seen_texts:
            return
        seen_texts.add(text)
        sync_ws_send({"type": "transcript", "text": text, "end_of_turn": True})
        
        if AUTO_ASSISTANT_REPLY:
            try:
                asyncio.run_coroutine_threadsafe(
                    process_transcript(session_id, text, ws_send), loop
                )
            except Exception as e:
                log.exception(f"Error processing transcript: {e}")
                
    def on_termination(client, event):
        dur = getattr(event, "audio_duration_seconds", 0)
        sync_ws_send({"type": "info", "message": "Session terminated", "duration": dur})
        
    def on_error(client, error):
        log.error(f"AssemblyAI error: {error}")
        sync_ws_send({"type": "error", "message": f"Speech recognition error: {str(error)}"})

    client.on(StreamingEvents.Begin, on_begin)
    client.on(StreamingEvents.Turn, on_turn)
    client.on(StreamingEvents.Termination, on_termination)
    client.on(StreamingEvents.Error, on_error)

    try:
        params = StreamingParameters(
            sample_rate=16000,
            format_turns=True,
            end_of_turn_confidence_threshold=0.75,
            min_end_of_turn_silence_when_confident=160,
            max_turn_silence=2400,
        )
        client.connect(params)
        await ws_send({"type": "info", "message": "Connected successfully"})
        
    except Exception as e:
        log.exception(f"AssemblyAI connection failed: {e}")
        await ws_send({"type": "error", "message": f"Connection failed: {str(e)}"})
        await websocket.close()
        return

    send_fn = getattr(client, "send_audio", None) or getattr(client, "send_bytes", None)
    streamer: QueueAudioStreamer | None = None
    if not callable(send_fn):
        streamer = QueueAudioStreamer(client)
        streamer.start()

    try:
        while True:
            msg = await websocket.receive()
            
            if "bytes" in msg and msg["bytes"]:
                try:
                    if streamer:
                        streamer.send(msg["bytes"])
                    else:
                        send_fn(msg["bytes"])
                except Exception as e:
                    log.error(f"Error sending audio: {e}")
                    break
                    
            elif "text" in msg and msg["text"]:
                text = msg["text"]
                if text == "__stop":
                    try:
                        client.disconnect(terminate=True)
                    except Exception:
                        pass
                    break
                else:
                    await ws_send({"type": "echo", "text": text})
                    
            elif msg.get("type") == "websocket.disconnect":
                break
                
    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        log.exception(f"WebSocket error for session {session_id}: {e}")
    finally:
        if streamer:
            streamer.stop()
        try:
            client.disconnect(terminate=True)
        except Exception:
            pass
        # Clean up session data
        if session_id in SESSION_KEYS:
            del SESSION_KEYS[session_id]
        log.info(f"Cleaned up session {session_id}")

# ---------------------- Debug Endpoints ----------------------
@app.get("/debug/persona/{session_id}")
async def debug_persona(session_id: str):
    return {
        "session_id": session_id,
        "current_persona": SESSION_PERSONA.get(session_id, "None set"),
        "available_personas": list(PERSONAS.keys()),
        "chat_history_length": len(CHAT_HISTORY.get(session_id, []))
    }

@app.get("/debug/chat/{session_id}")
async def debug_chat(session_id: str):
    return {
        "session_id": session_id,
        "chat_history": CHAT_HISTORY.get(session_id, []),
        "persona": SESSION_PERSONA.get(session_id, "Not set"),
        "api_keys": list(SESSION_KEYS.get(session_id, {}).keys())
    }

@app.post("/reset/{session_id}")
async def reset_session(session_id: str):
    if session_id in CHAT_HISTORY:
        del CHAT_HISTORY[session_id]
    if session_id in SESSION_PERSONA:
        del SESSION_PERSONA[session_id]
    if session_id in SESSION_KEYS:
        del SESSION_KEYS[session_id]
    return {"message": f"Session {session_id} reset successfully"}

# ---------------------- Entrypoint ----------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)