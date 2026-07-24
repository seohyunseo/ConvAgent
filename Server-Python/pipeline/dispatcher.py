"""
pipeline/dispatcher.py

Stage 3 — Dispatcher / Router
==============================
Consumes parsed transcript dicts from ``transcript_queue`` and performs
two actions for every transcript payload:

    Action A  Send the raw JSON payload to the Unity client immediately
              (via registered handlers, e.g. ResultSender).
              This ensures interim results appear in real-time on the headset.

    Action B  Pass the data to ``SessionMemory.add_transcript()``.
              Only ``isFinal=True`` entries are actually stored (the
              memory class silently drops interim results).

LLM trigger
-----------
The LLM pipeline is no longer fired by an internal buffer threshold.
Instead, ``_signal_listener`` watches ``signal_queue``.  When the Unity
client sends the string configured as ``LLM_TRIGGER_SIGNAL`` (config.py),
``AudioReceiver`` forwards it to ``signal_queue`` and the Dispatcher
snapshots the current context and spawns the LLM pipeline task.

Extensibility
-------------
Additional processing stages can be added as handlers:

    dispatcher.register_handler(my_module.process)   # ← add before sender
    dispatcher.register_handler(result_sender.send)

Sentinel Protocol
-----------------
A ``None`` value on ``transcript_queue`` or ``signal_queue`` signals
end-of-stream.  Both consumers exit cleanly when they receive it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from llm.llm_pipeline import run_pipeline
from memory.session_memory import SessionMemory


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type alias: any async callable that accepts a transcript dict
TranscriptHandler = Callable[[dict], Awaitable[Any]]


async def _run_pipeline_safe(
    context: str,
    utterance: str,
    client_id: str,
    send_callback: Callable[[dict], Awaitable[Any]],
    memory: SessionMemory,
) -> None:
    """
    Exception-safe wrapper around ``run_pipeline``.

    After a successful pipeline run, serialises the Step 4 result into a
    tagged payload and delivers it to the Unity client via ``send_callback``
    (which fans out to all registered Dispatcher handlers, i.e. ResultSender).

    Spawned as a fire-and-forget background task so that a Gemini API
    error never crashes the Dispatcher or the WebSocket session.
    """
    try:
        result = await run_pipeline(
            context_text=context,
            utterance_text=utterance,
            client_id=client_id,
            memory=memory,
        )

        logger.info(
            f"[{client_id}] LLM Pipeline completed. "
            f"Result keys: {list(result.keys())}"
        )

        # Build the payload sent back to Unity.
        # type='llm_result' lets the client distinguish this from STT transcripts.
        step4 = result.get("step4") or {}
        llm_payload: dict = {
            "type": "llm_result",
            "entity": step4.get("entity", ""),
            "description": step4.get("description", ""),
            # Include Step 3 score for debugging / analytics in Unity
            "step3": result.get("step3"),
        }

        logger.info(f"[{client_id}] Sending LLM result to client: {llm_payload}")
        await send_callback(llm_payload)

    except Exception as exc:
        logger.error(
            f"[{client_id}] LLM Pipeline raised an unhandled error: {exc}",
            exc_info=True,
        )


class Dispatcher:
    """
    Parameters
    ----------
    transcript_queue:
        Source of transcript payload dicts.  ``None`` = end of stream.
    signal_queue:
        Source of LLM trigger signals from the client.  ``None`` = end.
    client_id:
        Short identifier used in log messages.
    memory:
        The ``SessionMemory`` instance for this client session.
    """

    def __init__(
        self,
        transcript_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        client_id: str,
        memory: SessionMemory,
    ) -> None:
        self._transcript_queue = transcript_queue
        self._signal_queue = signal_queue
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
        Main coroutine.  Starts a ``_signal_listener`` sub-task to watch
        for LLM trigger signals, then processes the transcript queue until
        the EOF sentinel is received or the task is cancelled.
        """
        logger.info(f"[{self._client_id}] Dispatcher started.")
        signal_task = asyncio.create_task(
            self._signal_listener(),
            name=f"signal-listener-{self._client_id}",
        )
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
            signal_task.cancel()
            await asyncio.gather(signal_task, return_exceptions=True)
            logger.info(f"[{self._client_id}] Dispatcher finished.")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _signal_listener(self) -> None:
        """
        Concurrent sub-task that waits for LLM trigger signals.

        Runs alongside the main transcript loop.  Each signal received
        fires a new background LLM pipeline task.
        """
        logger.info(f"[{self._client_id}] Signal listener started.")
        try:
            while True:
                signal = await self._signal_queue.get()

                if signal is None:
                    logger.info(
                        f"[{self._client_id}] Signal listener received EOF — stopping."
                    )
                    break

                logger.info(
                    f"[{self._client_id}] [LLM TRIGGER] "
                    f"Signal '{signal}' received — spawning pipeline task."
                )
                await self._fire_llm_pipeline()

        except asyncio.CancelledError:
            logger.info(f"[{self._client_id}] Signal listener cancelled.")
        except Exception as exc:
            logger.error(
                f"[{self._client_id}] Signal listener error: {exc}", exc_info=True
            )
        finally:
            logger.info(f"[{self._client_id}] Signal listener finished.")

    async def _fire_llm_pipeline(self) -> None:
        """
        Snapshot current memory context and spawn a non-blocking LLM pipeline task.
        """
        context = self._memory.get_context()
        utterance = self._memory.get_last_utterance()

        # Capture handlers in a closure so the background task uses the
        # handler list active at trigger time.
        handlers = list(self._handlers)
        client_id = self._client_id

        async def _send_llm_result(result_payload: dict) -> None:
            for handler in handlers:
                try:
                    await handler(result_payload)
                except Exception as exc:
                    logger.error(
                        f"[{client_id}] LLM result handler error: {exc}",
                        exc_info=True,
                    )

        asyncio.create_task(
            _run_pipeline_safe(
                context=context,
                utterance=utterance,
                client_id=self._client_id,
                send_callback=_send_llm_result,
                memory=self._memory,
            ),
            name=f"llm-pipeline-{self._client_id}",
        )

    async def _dispatch(self, payload: dict) -> None:
        """
        Process one transcript payload.

        Action A — forward to all registered handlers (e.g. ResultSender)
                   so interim results reach the Unity client in real-time.
        Action B — persist to SessionMemory (final-only; interim ignored).

        LLM triggering (formerly Action C) is handled by _signal_listener.
        """
        # ── Action A: forward raw payload to WebSocket immediately ────────────
        # for handler in self._handlers:
        #     try:
        #         await handler(payload)
        #     except Exception as exc:
        #         logger.error(
        #             f"[{self._client_id}] Handler "
        #             f"'{getattr(handler, '__qualname__', repr(handler))}' "
        #             f"raised an error: {exc}",
        #             exc_info=True,
        #         )
        #         # Continue to next handler — one bad handler must not block

        # ── Action B: persist to session memory ──────────────────────────────
        # add_transcript() silently ignores isFinal=False entries.
        self._memory.add_transcript(
            speaker_tag=payload.get("speakerTag", 0),
            text=payload.get("transcript", ""),
            is_final=payload.get("isFinal", False),
        )
