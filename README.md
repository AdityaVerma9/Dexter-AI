# Voice-Agent
A voice-enabled conversational AI system that captures audio input from the browser, transcribes it to text, processes it with a Large Language Model (LLM), and returns a synthesized speech response.

## Overview

This project provides a browser-based interface connected to a FastAPI backend that integrates:

- **AssemblyAI** for speech-to-text (STT)
- **Google Gemini** for generating responses
- **Murf AI** for text-to-speech (TTS)

The system supports persistent conversation sessions and asynchronous processing with timeout handling to ensure responsiveness.

---

## Features

- Browser-based audio recording with start/stop controls
- Speech-to-text transcription
- LLM-based conversational responses with limited history
- Text-to-speech synthesis for AI responses
- Audio download capability
- Session-based conversation context
# Dexter-AI
