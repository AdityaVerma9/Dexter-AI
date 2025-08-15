import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    # API Keys
    MURF_API_KEY: str = os.getenv("MURF_API_KEY", "")
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # External endpoints & models
    MURF_TTS_ENDPOINT: str = os.getenv("MURF_TTS_ENDPOINT", "https://api.murf.ai/v1/speech/generate")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # Timeouts & history
    STT_TIMEOUT_SEC: int = int(os.getenv("STT_TIMEOUT_SEC", 18))
    LLM_TIMEOUT_SEC: int = int(os.getenv("LLM_TIMEOUT_SEC", 20))
    TTS_TIMEOUT_SEC: int = int(os.getenv("TTS_TIMEOUT_SEC", 25))
    HISTORY_MAX_MESSAGES: int = int(os.getenv("HISTORY_MAX_MESSAGES", 6))

    # Paths
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "uploads"))

settings = Settings()
# Ensure upload dir exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
