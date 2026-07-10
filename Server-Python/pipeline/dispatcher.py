"""
pipeline/dispatcher.py

Stage 3 — Dispatcher / Router
==============================
Consumes parsed transcript dicts from ``transcript_queue`` and performs
three actions for every payload:

    Action A  Send the raw JSON payload to the Unity client immediately
              (via registered handlers, e.g. ResultSender).
              This ensures interim results appear in real-time on the headset.

    Action B  Pass the data to ``SessionMemory.add_transcript()``.
              Only ``isFinal=True`` entries are actually stored (the
              memory class silently drops interim results).

    Action C  Check if ``len(memory.unprocessed_buffer) >= LLM_TRIGGER_THRESHOLD``.
              If the threshold is reached, log the context and clear the
              buffer.  This is the placeholder for the future LLM worker —
              swap the log statement for a real API call when ready.

Extensibility
-------------
Additional processing stages (e.g. intent detection, sentiment analysis)
can be added as handlers:

    dispatcher.register_handler(my_module.process)   # ← add before sender
    dispatcher.register_handler(result_sender.send)

Sentinel Protocol
-----------------
A ``None`` value on ``transcript_queue`` signals end-of-stream.
The Dispatcher exits cleanly when it receives this sentinel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from memory.session_memory import LLM_TRIGGER_THRESHOLD, SessionMemory

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type alias: any async callable that accepts a transcript dict
TranscriptHandler = Callable[[dict], Awaitable[Any]]


class Dispatcher:
    """
    Parameters
    ----------
    transcript_queue:
        Source of transcript payload dicts.  ``None`` = end of stream.
    client_id:
        Short identifier used in log messages.
    memory:
        The ``SessionMemory`` instance for this client session.
    """

    def __init__(
        self,
        transcript_queue: asyncio.Queue,
        client_id: str,
        memory: SessionMemory,
    ) -> None:
        self._transcript_queue = transcript_queue
        self._client_id = client_id
        self._memory = memory
        self._handlers: list[TranscriptHandler] = []

    # ------------------------------------------------------------------
    # Public — handler registration
    # ------------------------------------------------------------------

    def register_handler(self, handler: TranscriptHandler) -> None:
        """
        Register an async handler to be invoked for every transcript event.

        Handlers are called in the order they are registered.

        Parameters
        ----------
        handler:
            An ``async def fn(payload: dict) -> Any`` coroutine function.
        """
        self._handlers.append(handler)
        logger.debug(
            f"[{self._client_id}] Dispatcher: registered handler "
            f"'{getattr(handler, '__qualname__', repr(handler))}'."
        )

    # ------------------------------------------------------------------
    # Public — asyncio entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Main coroutine.  Runs until it receives the ``None`` sentinel
        or the task is cancelled.
        """
        logger.info(f"[{self._client_id}] Dispatcher started.")
        try:
            while True:
                payload = await self._transcript_queue.get()

                if payload is None:
                    logger.info(
                        f"[{self._client_id}] Dispatcher received EOF sentinel — stopping."
                    )
                    break

                await self._dispatch(payload)

        except asyncio.CancelledError:
            logger.info(f"[{self._client_id}] Dispatcher cancelled.")
            raise
        except Exception as exc:
            logger.error(
                f"[{self._client_id}] Dispatcher error: {exc}", exc_info=True
            )
        finally:
            logger.info(f"[{self._client_id}] Dispatcher finished.")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _dispatch(self, payload: dict) -> None:
        """
        Process one transcript payload through all three pipeline actions.
        """
        # ── Action A: forward raw payload to WebSocket immediately ─────
        # This delivers interim results in real-time to the Unity headset.
        for handler in self._handlers:
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    f"[{self._client_id}] Handler "
                    f"'{getattr(handler, '__qualname__', repr(handler))}' "
                    f"raised an error: {exc}",
                    exc_info=True,
                )
                # Continue to the next handler — one bad handler must not
                # block the pipeline

        # ── Action B: persist to session memory ────────────────────────
        # add_transcript() silently ignores isFinal=False entries.
        self._memory.add_transcript(
            speaker_tag=payload.get("speakerTag", 0),
            text=payload.get("transcript", ""),
            is_final=payload.get("isFinal", False),
        )

        # ── Action C: (placeholder) LLM trigger ────────────────────────
        # When enough unprocessed sentences have accumulated, fire the
        # LLM processing pipeline.  Replace the log statement below with
        # a real LLM API call (e.g. asyncio.create_task(llm_worker.run()))
        # when you are ready to integrate.
        if len(self._memory.unprocessed_buffer) >= LLM_TRIGGER_THRESHOLD:
            context = self._memory.get_context()
            logger.info(
                f"[{self._client_id}] [LLM TRIGGER] "
                f"Unprocessed buffer reached {LLM_TRIGGER_THRESHOLD} items. "
                f"Triggering LLM processing with context:\n{context}"
            )
            self._memory.clear_unprocessed()
