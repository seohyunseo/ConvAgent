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

DEFAULT_CONTEXT_WINDOW: int = 5
LLM_TRIGGER_THRESHOLD: int = 3