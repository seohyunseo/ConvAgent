"""
config.py — Central configuration for the ConvAgent Middleware Server.

All tuneable constants live here so no magic numbers are scattered
across the codebase.  Authentication for Google Cloud is handled
implicitly via the GOOGLE_APPLICATION_CREDENTIALS environment variable.
"""

# ---------------------------------------------------------------------------
# WebSocket Server
# ---------------------------------------------------------------------------
WS_HOST: str = "0.0.0.0"
WS_PORT: int = 8080

# ---------------------------------------------------------------------------
# Audio Input
# ---------------------------------------------------------------------------
AUDIO_SAMPLE_RATE: int = 48_000   # Hz  (must match Unity client)
AUDIO_LANGUAGE: str = "ko-KR"

# ---------------------------------------------------------------------------
# Google STT — Speaker Diarization
# ---------------------------------------------------------------------------
DIARIZATION_MIN_SPEAKERS: int = 2
DIARIZATION_MAX_SPEAKERS: int = 4

# ---------------------------------------------------------------------------
# Internal Queue Sizes  (0 = unlimited)
# ---------------------------------------------------------------------------
AUDIO_QUEUE_MAXSIZE: int = 0
TRANSCRIPT_QUEUE_MAXSIZE: int = 0
THREAD_QUEUE_TIMEOUT: float = 0.5

# ---------------------------------------------------------------------------
# Session Memory
# ---------------------------------------------------------------------------
DEFAULT_CONTEXT_WINDOW: int = 5

# ---------------------------------------------------------------------------
# LLM Trigger — string the Unity client sends to fire the pipeline
# ---------------------------------------------------------------------------
LLM_TRIGGER_SIGNAL: str = "trigger LLM"

# ---------------------------------------------------------------------------
# Vertex AI / Gemini  — set VERTEX_PROJECT_ID to your GCP project ID
# ---------------------------------------------------------------------------
VERTEX_PROJECT_ID: str = "still-emissary-501810-q7"
VERTEX_LOCATION: str = "us-central1"
GEMINI_MODEL: str = "gemini-2.5-flash"