"""
session.py — ClientSession

Encapsulates the complete lifecycle of a single connected WebSocket client:
queues, pipeline tasks, and clean teardown on disconnect.

Pipeline Topology
-----------------

    ┌─────────────────────────────────────────────────────────────┐
    │                      ClientSession                          │
    │                                                             │
    │  WebSocket ──► [AudioReceiver] ──► audio_queue              │
    │                                        │                    │
    │                                   [STTWorker]               │
    │                                        │                    │
    │                                  transcript_queue           │
    │                                        │                    │
    │                                  [Dispatcher]               │
    │                                        │                    │
    │                               ┌────────┴────────┐           │
    │                          (now)│         (future)│           │
    │                        [ResultSender]      [LLMModule]      │
    │                               │                             │
    │                          WebSocket ◄────────────────────────┘
    └─────────────────────────────────────────────────────────────┘

To add a future LLM module:
    dispatcher.register_handler(my_llm_module.process)   # ← add before
    dispatcher.register_handler(result_sender.send)
"""

import asyncio
import logging
import uuid

from config import AUDIO_QUEUE_MAXSIZE, TRANSCRIPT_QUEUE_MAXSIZE
from memory import SessionMemory
from pipeline import AudioReceiver, Dispatcher, ResultSender, STTWorker

logger = logging.getLogger(__name__)


class ClientSession:
    """
    One instance per connected client.

    Usage
    -----
        session = ClientSession(websocket)
        await session.run()  # blocks until disconnect + cleanup
    """

    def __init__(self, websocket) -> None:
        # Short ID (first 8 chars of UUID) for readable log lines
        self.client_id: str = uuid.uuid4().hex[:8]
        self._websocket = websocket

        self._audio_queue: asyncio.Queue = asyncio.Queue(
            maxsize=AUDIO_QUEUE_MAXSIZE
        )
        self._transcript_queue: asyncio.Queue = asyncio.Queue(
            maxsize=TRANSCRIPT_QUEUE_MAXSIZE
        )
        self._memory: SessionMemory = SessionMemory(self.client_id)
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Build the pipeline, run all tasks concurrently, and clean up
        when they finish (or when the client disconnects).
        """
        remote = getattr(self._websocket, "remote_address", "unknown")
        logger.info(
            f"[{self.client_id}] ── New client session ──  "
            f"remote={remote}"
        )

        try:
            self._build_pipeline()
            # Wait for all pipeline tasks; gather returns exceptions instead
            # of re-raising so every task gets a chance to finish
            results = await asyncio.gather(
                *self._tasks, return_exceptions=True
            )
            for task, result in zip(self._tasks, results):
                if isinstance(result, Exception) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    logger.error(
                        f"[{self.client_id}] Task '{task.get_name()}' "
                        f"raised: {result}",
                        exc_info=result,
                    )
        finally:
            await self._cleanup()
            logger.info(
                f"[{self.client_id}] ── Session fully cleaned up ──"
            )

    # ------------------------------------------------------------------
    # Private — pipeline wiring
    # ------------------------------------------------------------------

    def _build_pipeline(self) -> None:
        """
        Instantiate all pipeline stages and wire them together via
        shared queues and handler registration.
        """
        audio_receiver = AudioReceiver(
            websocket=self._websocket,
            audio_queue=self._audio_queue,
            client_id=self.client_id,
        )
        stt_worker = STTWorker(
            audio_queue=self._audio_queue,
            transcript_queue=self._transcript_queue,
            client_id=self.client_id,
        )
        result_sender = ResultSender(
            websocket=self._websocket,
            client_id=self.client_id,
        )
        dispatcher = Dispatcher(
            transcript_queue=self._transcript_queue,
            client_id=self.client_id,
            memory=self._memory,
        )

        # ── Register handlers in processing order ─────────────────────
        # TODO: insert LLM / intent module handlers here in the future:
        #   dispatcher.register_handler(llm_module.process)
        dispatcher.register_handler(result_sender.send)

        # ── Create asyncio Tasks ──────────────────────────────────────
        self._tasks = [
            asyncio.create_task(
                audio_receiver.run(),
                name=f"audio-receiver-{self.client_id}",
            ),
            asyncio.create_task(
                stt_worker.run(),
                name=f"stt-worker-{self.client_id}",
            ),
            asyncio.create_task(
                dispatcher.run(),
                name=f"dispatcher-{self.client_id}",
            ),
        ]

        logger.info(
            f"[{self.client_id}] Pipeline built — "
            f"{len(self._tasks)} tasks started."
        )

    # ------------------------------------------------------------------
    # Private — teardown
    # ------------------------------------------------------------------

    async def _cleanup(self) -> None:
        """
        Cancel any tasks that are still running and await them so that
        no fire-and-forget coroutines are left dangling.
        """
        pending = [t for t in self._tasks if not t.done()]
        if not pending:
            return

        logger.info(
            f"[{self.client_id}] Cancelling {len(pending)} "
            f"still-running task(s)."
        )
        for task in pending:
            task.cancel()

        # Await all to let them honour CancelledError cleanly
        await asyncio.gather(*pending, return_exceptions=True)
        logger.info(f"[{self.client_id}] All tasks cancelled and awaited.")
