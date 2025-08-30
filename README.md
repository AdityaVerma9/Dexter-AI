# 🎙️ Dexter AI — Streaming Voice Agent

![FastAPI](https://img.shields.io/badge/FastAPI-🚀-green?style=for-the-badge) ![WebSockets](https://img.shields.io/badge/WebSockets-Live-orange?style=for-the-badge)

**Dexter AI** is a persona-driven, real-time **streaming voice agent** 🗣️. It listens to your microphone, understands you through **speech-to-text (STT)**, reasons with an **LLM**, and replies with **text-to-speech (TTS)** — all in real time ⚡. Default persona: *Dexter Morgan* 🩸.

It’s built on **FastAPI** with a clean, modular service design. Beyond conversations, it can fetch you **latest news** 📰, **weather updates** 🌦️, and handle **file uploads & transcriptions** 🎧.

---

## 📑 Table of Contents
- [✨ Project Summary](#-project-summary)
- [🔑 Key Functionalities](#-key-functionalities)
- [🏗️ Architecture](#️-architecture)
- [🛠️ Technologies](#️-technologies)
- [⚙️ Features & Endpoints](#️-features--endpoints)
- [⚡ Running Locally](#-running-locally)
- [🚀 Future Improvements](#-future-improvements)

---

## ✨ Project Summary
Dexter AI demonstrates a modern streaming assistant pipeline:
1. **Browser Client** → captures mic 🎤 → streams audio to server via **WebSocket**.
2. **Server (FastAPI)** → orchestrates:
   - 🔊 **AssemblyAI** → transcribes speech → text.
   - 🧠 **Google GenAI** → generates context-aware responses.
   - 🎶 **Murf TTS** → speaks back with lifelike voice.
   - 📡 **News & Weather APIs** → supplement responses.
3. **Client Playback** → streams back transcript & audio → plays response.

---

## 🔑 Key Functionalities
✅ **Real-time speech streaming** via WebSocket  
✅ **AssemblyAI STT** for instant transcription  
✅ **LLM-powered responses** using Google GenAI  
✅ **Murf TTS** for natural voice replies  
✅ **NewsAPI** 📰 & **WeatherAPI** 🌦️ integrations  
✅ **Session-based API keys & personas** 🎭  
✅ **File uploads & offline transcription** 🎧  
✅ **Browser client UI** with microphone capture & playback  

---

## 🏗️ Architecture

### Detailed Flow
```mermaid
graph TD;
  subgraph Browser Client
    A1[Microphone Input]
    A2[Encode Audio Chunks]
    A3[Open WebSocket]
    A1 --> A2 --> A3
  end

  subgraph FastAPI Server
    B1[WS Handler (/ws/stream)]
    B2[Session Manager (state.py)]
    B3[STT Service → AssemblyAI]
    B4[LLM Service → Google GenAI]
    B5[TTS Service → Murf]
    B6[News Service]
    B7[Weather Service]
    B8[History & Persona Manager]
    
    A3 --> B1
    B1 --> B2
    B1 --> B3
    B3 --> B4
    B4 --> B5
    B4 --> B6
    B4 --> B7
    B2 --> B8
  end

  subgraph External Services
    C1[assembly.ai STT API]
    C2[google.genai LLM API]
    C3[murf TTS API]
    C4[News API]
    C5[Weather API]

    B3 --> C1
    B4 --> C2
    B5 --> C3
    B6 --> C4
    B7 --> C5
  end

  subgraph Browser Playback
    D1[Display Live Transcript]
    D2[Play TTS Audio]
    B5 --> D2
    B4 --> D1
  end

---

## 🛠️ Technologies
- **Backend:** FastAPI, Uvicorn, AsyncIO, WebSockets
- **LLM:** Google Generative AI (Gemini)
- **STT:** AssemblyAI
- **TTS:** Murf
- **Integrations:** NewsAPI, WeatherAPI
- **Client:** HTML + JS (WebSocket streaming, mic capture)
- **Infra Tools:** dotenv, aiohttp/httpx

---

## ⚙️ Features & Endpoints

### 🌐 WebSocket
- `ws://<host>/ws/stream` → real-time pipeline (mic → STT → LLM → TTS).

### 📡 REST Endpoints
- `/upload` → upload audio file
- `/transcribe/file` → offline transcription
- `/api/weather?city=London` → fetch weather
- `/api/news?country=us` → fetch news
- `/history/{session_id}` → get chat history
- `/debug/*` → debugging endpoints

---

## ⚡ Running Locally

### 🔧 Setup
```bash
# 1️⃣ Clone repo
 git clone <repo_url>
 cd Dexter-AI

# 2️⃣ Create virtual env
 python -m venv venv
 source venv/bin/activate   # macOS/Linux
 venv\Scripts\activate      # Windows

# 3️⃣ Install requirements
 pip install -r requirements.txt

# 4️⃣ Setup env vars (.env)
 cp .env.example .env
 # Add your API keys (AssemblyAI, Murf, GenAI, News, Weather)

# 5️⃣ Run server
 uvicorn main:app --reload --port 8000

# 6️⃣ Open in browser
 http://localhost:8000/
```

🎉 Done! Speak into your mic and Dexter AI will answer back 🗣️ → 🧠 → 🎶

---

## 🚀 Future Improvements
- 💾 **Persistent storage** (Redis / DB) for session history
- 🔐 **Secure API key management**
- 📈 **Scalability**: worker queues, rate limits
- 🎨 **UI upgrades**: multiple voices, adjustable pitch/rate
- ✅ **CI/CD pipeline** & tests

---

## 📜 License
MIT License — free to use, modify & share 🚀