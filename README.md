# Dexter AI — Streaming Voice Agent

**Dexter AI** is a streaming voice agent / voice assistant built with FastAPI. It provides a real‑time microphone streaming UI (browser) and server side pipeline that converts live audio → speech‑to‑text (STT) → LLM reasoning/response → text‑to‑speech (TTS) and returns audio and transcripts to the client. The project was implemented as a persona-driven voice agent (default persona: *Dexter Morgan*) and includes helpful integrations such as live news and weather lookups.

---

## Table of contents
- Project summary
- Key functionalities
- Architecture (high level)
- Technologies & libraries
- Features & endpoints
- Configuration / environment variables
- Running locally
- Notes & extension ideas

---

## Project summary
Dexter AI exemplifies a modern streaming voice assistant architecture: browser captures microphone audio and streams it via WebSocket to a FastAPI server. The server relays audio to a speech‑to‑text provider (AssemblyAI) using their streaming API, receives transcriptions, forwards the text to a generative LLM (Google GenAI / `google.genai` is used in the project), generates conversational responses, synthesizes audio using a TTS provider (Murf), and streams back transcripts and audio URLs to the client for playback. The app also provides REST endpoints for file uploads, batch transcription, TTS and fetching news/weather.

---

## Key functionalities (what the project does)
- **Real‑time microphone streaming** from browser → server via WebSocket.
- **Streaming STT (AssemblyAI)**: server connects to AssemblyAI via websocket and sends audio chunks for near‑real‑time transcription.
- **LLM integration (Google GenAI)**: transcribed text is sent to a generative model and streamed responses are relayed back to the client.
- **Text‑to‑Speech (Murf)**: generated LLM text can be converted to an audio file (URL) and returned so the client can play the response.
- **File upload + offline transcription** endpoints for uploading `.webm`/.`wav` audio and getting back transcripts or TTS audio.
- **News & Weather integrations**: REST endpoints that fetch headlines (NewsAPI) and weather (WeatherAPI) and return simple structured results.
- **Session management & per‑session API keys**: supports passing API keys per session (query params or session-level state) so a single server can hold multiple user/session keys in memory.
- **Persona support**: default persona (Dexter Morgan) and a mechanism for persona state per session — influences LLM prompts.
- **Legacy compatibility endpoints**: older/compat endpoints preserved for integration with older clients.

---

## High‑level architecture

Client (browser)
  • Records mic audio, manages audio buffers, and posts audio chunks over a WebSocket connection (`/ws/stream`).
  • Receives JSON messages containing partial or final transcriptions, LLM text, and audio URLs to play.

FastAPI server (`main.py`, `app/api`)
  • WebSocket handler (`/ws/stream`) accepts audio and meta messages from the client.
  • Uses a streaming strategy to forward audio to AssemblyAI and to receive streaming transcripts.
  • Orchestrates calls to `app/services/llm_service.py` (Google GenAI), `tts_service.py` (Murf), `stt_service.py` (AssemblyAI wrapper), `news_service.py` and `weather_service.py`.
  • Exposes REST endpoints (upload/transcribe/tts/news/weather/history) for non‑streaming use cases.
  • Keeps ephemeral session state (in `app/state.py`) such as per‑session API keys and persona.

External services
  • AssemblyAI — streaming speech‑to‑text.
  • Google GenAI (`google.genai`) — LLM for natural language responses.
  • Murf — TTS audio generation.
  • NewsAPI / WeatherAPI — supplemental info providers for fetching headlines and weather.

---

## Technologies & libraries
- Python (modern versions; code was developed for Python 3.12+)
- FastAPI (HTTP + WebSocket server)
- `websockets` and `asyncio` for async streaming
- AssemblyAI Python SDK for streaming STT
- Google Generative AI (`google.genai`) client for LLM interaction
- Murf TTS integration (via HTTP API / `httpx`)
- `aiohttp` / `httpx` for external HTTP calls
- Jinja2 Templates + static JavaScript client for browser capture
- `dotenv` for `.env`‑based configuration
- `uvicorn` as ASGI server for local running

Third‑party services:
- AssemblyAI (speech‑to‑text)
- Murf (text‑to‑speech)
- Google Generative AI (LLM)
- NewsAPI
- WeatherAPI

---

## Main features & API endpoints
(implemented in `main.py` and `app/api/routes.py`)

### WebSocket (real‑time)
- `ws://<host>/ws/stream` — primary streaming endpoint.
  - Query params supported: `session` (session id), `aai` (AssemblyAI key), `murf` (Murf key), `gemini` (GenAI key), `news`, `weather` (per‑session keys).
  - Flow: client sends audio chunks → server forwards to AssemblyAI → server sends partial & final transcripts back to client → server calls LLM and returns streamed LLM text and TTS audio URLs.

### REST endpoints (selected)
- `GET /` — serves the HTML UI when present.
- `GET /health` — health check endpoint.
- `POST /upload` — upload an audio file; returns saved metadata (filename, size).
- `POST /transcribe/file` — upload + transcribe a file via AssemblyAI in a request/response manner.
- `GET /api/weather?city=<city>&api_key=<key>` — get weather for given city.
- `GET /api/news?country=us` — fetch top headlines.
- `GET /history/{session_id}` — get recent chat history for the session.
- Legacy endpoints under `/legacy/*` for older client compatibility (e.g., `/legacy/tts/echo`, `/legacy/llm/query`, `/legacy/agent/chat/{session_id}`).

### Debugging endpoints (server)
- `GET /debug/persona/{session_id}` — inspect persona state.
- `GET /debug/chat/{session_id}` — inspect session chat history.
- `POST /reset/{session_id}` — reset session state.

---

## Configuration / environment variables
The project uses a `.env` file. Key environment variables expected by the code:
- `MURF_API_KEY` — Murf TTS API key
- `ASSEMBLYAI_API_KEY` — AssemblyAI API key
- `GEMINI_API_KEY` — Google GenAI API key
- `NEWSAPI_KEY` — NewsAPI key (optional)
- `WEATHER_API_KEY` — WeatherAPI key (optional)

Timeouts & other defaults exposed via env:
- `STT_TIMEOUT_SEC`, `LLM_TIMEOUT_SEC`, `TTS_TIMEOUT_SEC`, `HISTORY_MAX_MESSAGES`
- `GEMINI_MODEL` — default LLM model to use (e.g. `gemini-2.0-flash`)
- `UPLOAD_DIR` — where uploads are stored (defaults to `uploads`)

Be sure to create a `.env` file (the repository supplies a sample `.env` file) and populate keys for your chosen providers.

---

## Running locally (quick start)
1. Create a Python virtualenv and activate it.
2. Install requirements: `pip install -r requirements.txt`.
3. Create a `.env` file and export the required API keys.
4. Run the server locally:

```bash
uvicorn main:app --reload --port 8000
```

5. Open `http://localhost:8000/` in your browser to use the included UI (if templates are present) or connect with a WebSocket client to `/ws/stream`.

Notes:
- The project uses in‑memory session state (`app/state.py`) — for production, consider a persistent store like Redis.
- When using AssemblyAI streaming, ensure the SDK and keys are correct and note provider quotas/limits.

---

## Where to look (important files)
- `main.py` — server entrypoint, WebSocket orchestration, persona management.
- `app/api/routes.py` — REST endpoints for uploads, transcription, news/weather and legacy endpoints.
- `app/services/` — modular service wrappers:
  - `stt_service.py` — AssemblyAI wrapper for file transcription.
  - `llm_service.py` — Google GenAI streaming helpers.
  - `tts_service.py` — Murf TTS helper returning audio file URLs.
  - `news_service.py` / `weather_service.py` — integration helpers for news & weather.
- `app/utils/` — config, file helpers, and logger.
- `static/script.js` — client‑side JS for microphone capture and websocket streaming.

---

## Limitations & next steps (ideas)
- **Persistence:** store session history, personas, and user API keys in Redis or a database.
- **Security:** never store user API keys long term in plaintext; add encryption and authentication.
- **Scaling:** move STT/LLM/TTS calls into worker queues to avoid blocking; use rate limiting.
- **Fallbacks:** add optional fallbacks for STT or TTS providers.
- **Testing:** add unit/integration tests and CI.
- **UI improvements:** more robust latency handling, allow selecting voices, controlling speaking rate, and a conversation UI.

---

## License & attribution
Add whichever license you prefer (e.g., MIT). This repository contains 3rd‑party SDK usage — be mindful of each provider's terms of service.

---

If you want, I can:
- generate a `README.md` file in the repo (I already prepared one here),
- create a quick `docker-compose` + `Dockerfile` example for local dev,
- or produce example client code for connecting to `/ws/stream` (browser + Node) and demonstrate exact message formats.

Tell me which of the above you'd like next.

