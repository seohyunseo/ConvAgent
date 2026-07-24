"""
memory/session_memory.py

SessionMemory
=============
Manages the conversation history for a single client session.
It is the source-of-truth that LLM workers read from.

Data stored per entry
---------------------
    {
        "speaker":   int,    # diarized speaker tag (0 = unknown)
        "text":      str,    # finalised transcript text
        "timestamp": float,  # unix timestamp of when it was recorded
    }

Lifecycle
---------
                      Dispatcher
                          |
              isFinal=True transcripts only
                          |
                          v
              SessionMemory.add_transcript()
                          |
                          v
                      history[]
                     (permanent)
"""

import logging
import time
from config import DEFAULT_CONTEXT_WINDOW

logger = logging.getLogger(__name__)


class SessionMemory:
    """
    Parameters
    ----------
    client_id:
        Short identifier used in log messages.
    """

    def __init__(self, client_id: str) -> None:
        self._client_id = client_id

        # Permanent, append-only record of every final transcript
        self.history: list[dict] = []

        self.entity_memory: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_transcript(self, speaker_tag: int, text: str, is_final: bool) -> None:
        """
        Record a transcript entry.

        Silently ignores ``is_final=False`` interim results — only
        stable, finalised text is worth storing in memory.

        Parameters
        ----------
        speaker_tag:
            Diarization speaker index.  0 = unknown / interim.
        text:
            Recognised transcript text.
        is_final:
            Must be ``True`` for the entry to be stored.
        """
        if not is_final:
            return  # discard interim results silently

        entry: dict = {
            "speaker": speaker_tag,
            "text": text,
            "timestamp": time.time(),
        }

        self.history.append(entry)

        logger.info(
            f"[{self._client_id}] Memory: stored final transcript "
            f"(speaker={speaker_tag}) '{text}' "
            f"| history={len(self.history)}"
        )

    def add_entity_memory(self, entity: str) -> None:
        """
        Record an entity memory entry.

        Parameters
        ----------
        entity:
            Entity memory entry.
        """
        self.entity_memory.append(entity)
        logger.info(
            f"[{self._client_id}] Memory: stored entity memory - {entity} | entity_memory={len(self.entity_memory)}"
        )

    def get_entity_memory(self) -> list[str]:
        """
        Return the entity memory.

        Returns
        -------
        list[str]
            Entity memory.
        """
        return self.entity_memory

    def get_context(self, window_size: int = DEFAULT_CONTEXT_WINDOW) -> str:
        """
        Return the last *window_size* sentences from history as a
        human-readable string, suitable for inclusion in an LLM prompt.

        Example output::

            Speaker 1: 안녕하세요
            Speaker 2: 반갑습니다
            Speaker 1: 오늘 날씨가 좋네요

        Parameters
        ----------
        window_size:
            Maximum number of history entries to include.

        Returns
        -------
        str
            Formatted context string.  Empty string if history is empty.
        """
        recent = self.history[-(window_size+1):-1]
        return "\n".join(
            f"Speaker {entry['speaker']}: {entry['text']}"
            for entry in recent
        )

    def get_last_utterance(self) -> str:
        """
        Return the last utterance from the history.

        Returns
        -------
        str
            Last utterance text. Empty string if history is empty.
        """
        return self.history[-1]["text"] if self.history else ""


    # ------------------------------------------------------------------
    # Convenience / introspection
    # ------------------------------------------------------------------

    @property
    def total_turns(self) -> int:
        """Total number of finalised turns recorded in this session."""
        return len(self.history)

    def __repr__(self) -> str:
        return (
            f"<SessionMemory client={self._client_id} "
            f"history={len(self.history)}>"
        )
