"""
pipeline/dispatcher.py

Stage 3 — Dispatcher / Router
==============================
Consumes parsed transcript dicts from ``transcript_queue`` and fans
them out to one or more registered *handler* coroutines.

Extensibility
-------------
This is the designated **interception point** for future processing
stages.  To add an LLM module, simply register its async handler
*before* the ResultSender's handler in ``session.py``:

    dispatcher.register_handler(llm_module.process)   # new stage
    dispatcher.register_handler(result_sender.send)   # existing stage

Handlers are called **sequentially** in registration order for every
incoming payload.  A handler that raises an exception is logged and
skipped; subsequent handlers still run.

Sentinel Protocol
-----------------
A ``None`` value on ``transcript_queue`` signals end-of-stream.
The Dispatcher exits cleanly when it receives this sentinel.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

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
    """

    def __init__(
        self,
        transcript_queue: asyncio.Queue,
        client_id: str,
    ) -> None:
        self._transcript_queue = transcript_queue
        self._client_id = client_id
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

                # logger.debug(
                #     f"[{self._client_id}] Dispatcher routing: "
                #     f"final={payload.get('isFinal')}, "
                #     f"speaker={payload.get('speakerTag')}, "
                #     f"text='{payload.get('transcript', '')[:60]}…'"
                # )

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
        """Fan out one payload to every registered handler in order."""
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
                # Continue to the next handler — don't let one bad handler
                # block the others
