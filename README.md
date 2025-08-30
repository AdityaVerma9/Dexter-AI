# 🎙️ Dexter AI — Streaming Voice Agent

![FastAPI](https://img.shields.io/badge/FastAPI-🚀-green?style=for-the-badge) ![WebSockets](https://img.shields.io/badge/WebSockets-Live-orange?style=for-the-badge)

**Dexter AI** is a persona-driven, real-time **streaming voice agent**. It listens to your microphone, understands you through **speech-to-text (STT)**, reasons with an **LLM**, and replies with **text-to-speech (TTS)** — all in real time. Default persona: *Dexter Morgan*.

It’s built on **FastAPI** with a clean, modular service design. Beyond conversations, it can fetch **news**, **weather updates**, and handle **file uploads & transcriptions**.

---

## 📑 Table of Contents
- [Project Summary](#project-summary)
- [Key Functionalities](#key-functionalities)
- [Architecture](#architecture)
- [Sequence Diagram](#sequence-diagram)
- [Technologies](#technologies)
- [Features & Endpoints](#features--endpoints)
- [Running Locally](#running-locally)
- [Future Improvements](#future-improvements)

---

## Project Summary
Dexter AI demonstrates a modern streaming assistant pipeline:
1. **Browser Client** captures microphone audio and streams it to the server via WebSocket.
2. **FastAPI Server** orchestrates STT (AssemblyAI), LLM (Google GenAI), and TTS (Murf), plus news/weather lookups.
3. **Client Playback** receives live transcripts and audio replies for playback.

---

## Key Functionalities
- Real-time speech streaming via WebSocket
- Streaming STT with AssemblyAI
- LLM-powered conversational responses (Google GenAI)
- TTS replies via Murf
- NewsAPI & WeatherAPI integrations
- Session-based API keys and persona state
- File upload and offline transcription endpoints
- Browser client with microphone capture and playback

---

## Architecture

### Detailed Flow
```mermaid
flowchart TD
  %% Browser client
  subgraph Browser_Client
    A1["Microphone Input"]
    A2["Encode Audio Chunks"]
    A3["Open WebSocket (/ws/stream)"]
    A1 --> A2
    A2 --> A3
  end

  %% FastAPI Server internals
  subgraph FastAPI_Server
    B1["WS Handler (/ws/stream)"]
    B2["Session Manager (state.py)"]
    B3["STT Service: AssemblyAI"]
    B4["LLM Service: Google GenAI"]
    B5["TTS Service: Murf"]
    B6["News Service"]
    B7["Weather Service"]
    B8["History & Persona Manager"]
  end

  %% External APIs
  subgraph External_Services
    C1["assembly.ai STT API"]
    C2["google.genai LLM API"]
    C3["murf TTS API"]
    C4["News API"]
    C5["Weather API"]
  end

  %% Browser playback
  subgraph Browser_Playback
    D1["Display Live Transcript"]
    D2["Play TTS Audio"]
  end

  %% Connections
  A3 --> B1
  B1 --> B2
  B1 --> B3
  B3 --> B4
  B4 --> B5
  B4 --> B6
  B4 --> B7
  B2 --> B8

  B3 --> C1
  B4 --> C2
  B5 --> C3
  B6 --> C4
  B7 --> C5

  B5 --> D2
  B4 --> D1
```

---

## Sequence Diagram
Use this mermaid sequence diagram to show step-by-step message exchange. Paste into a fenced `mermaid` block in your README.

```mermaid
sequenceDiagram
  participant Browser
  participant Server
  participant AssemblyAI
  participant GenAI
  participant Murf

  Browser->>Server: Open WebSocket (/ws/stream)
  Browser->>Server: Send audio chunk (binary)
  Server->>AssemblyAI: Forward audio chunk (stream)
  AssemblyAI-->>Server: Partial transcript (stream)
  Server->>GenAI: Send transcript + context
  GenAI-->>Server: Streamed LLM tokens / partial response
  Server->>Murf: Request TTS for final text
  Murf-->>Server: Return TTS audio (URL or binary)
  Server-->>Browser: Send transcript + audio URL / playback command
  Browser->>Browser: Play audio, display transcript
```

---

## Technologies
- Backend: FastAPI, Uvicorn, AsyncIO, WebSockets
- LLM: Google Generative AI (Gemini)
- STT: AssemblyAI
- TTS: Murf
- Integrations: NewsAPI, WeatherAPI
- Client: HTML + JS (WebSocket streaming, mic capture)
- Tools: dotenv, aiohttp/httpx

---

## Features & Endpoints

### WebSocket
- `ws://<host>/ws/stream` → real-time pipeline (mic → STT → LLM → TTS).

### REST Endpoints
- `/upload` → upload audio file
- `/transcribe/file` → offline transcription
- `/api/weather?city=London` → fetch weather
- `/api/news?country=us` → fetch news
- `/history/{session_id}` → get chat history
- `/debug/*` → debugging endpoints

---

## Running Locally

### Setup
```bash
# 1. Clone repo
git clone <repo_url>
cd Dexter-AI

# 2. Create virtual env
python -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install requirements
pip install -r requirements.txt

# 4. Setup env vars (.env)
cp .env.example .env
# Add your API keys (ASSEMBLYAI, MURF, GEMINI/GENAI, NEWSAPI, WEATHER_API)

# 5. Run server
uvicorn main:app --reload --port 8000

# 6. Open in browser
http://localhost:8000/
```

Notes:
- Ensure your `.env` includes valid API keys.
- For production, consider using a process manager (gunicorn/uvicorn workers) and a persistent store (Redis) for session state.

---

## Future Improvements
- Persistent storage for session history
- Secure API key management (vault/encryption)
- Scalability (worker queues, rate limiting)
- UI improvements (voice selection, rate/pitch control)
- CI/CD and tests

---

## License
MIT License — free to use, modify & share
