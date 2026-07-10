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
AUDIO_SAMPLE_RATE: int = 16_000   # Hz  (must match Unity client)
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
THREAD_QUEUE_TIMEOUT: float = 1.0

# ---------------------------------------------------------------------------
# MEMORY BUFFER SIZES & LLM THRESHOLD
# ---------------------------------------------------------------------------

DEFAULT_CONTEXT_WINDOW: int = 5
LLM_TRIGGER_THRESHOLD: int = 3

# ---------------------------------------------------------------------------
# Vertex AI / Gemini  — set VERTEX_PROJECT_ID to your GCP project ID
# ---------------------------------------------------------------------------
VERTEX_PROJECT_ID: str = "still-emissary-501810-q7"
VERTEX_LOCATION: str = "us-central1"
GEMINI_MODEL: str = "gemini-2.5-flash"