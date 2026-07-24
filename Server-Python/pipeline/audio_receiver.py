"""
pipeline/audio_receiver.py
Stage 1 — AudioReceiver
========================
Reads raw PCM audio bytes from the WebSocket connection and enqueues
them into ``audio_queue`` for downstream consumption by the STTWorker.

Also handles text-frame signals from the client.  If the received text
matches ``LLM_TRIGGER_SIGNAL`` (config.py), it is forwarded to
``signal_queue`` so the Dispatcher can fire the LLM pipeline on demand.

Responsibilities
----------------
- Iterate over incoming WebSocket messages.
- Binary frames  → ``audio_queue`` (STTWorker)
- Trigger text   → ``signal_queue`` (Dispatcher signal listener)
- Other text     → log warning and ignore
- On connection close or any error, push ``None`` sentinels to both
  queues so downstream workers exit cleanly.
"""
import asyncio
import logging
import websockets.exceptions
from config import LLM_TRIGGER_SIGNAL
logger = logging.getLogger(__name__)
class AudioReceiver:
    """
    Parameters
    ----------
    websocket:
        The active WebSocket connection for this client.
    audio_queue:
        Asyncio queue that receives ``bytes`` chunks.
        A ``None`` sentinel is pushed when the stream ends.
    signal_queue:
        Asyncio queue that receives trigger strings from the client.
        A ``None`` sentinel is pushed when the stream ends.
    client_id:
        Short identifier used in log messages.
    """
    def __init__(
        self,
        websocket,
        audio_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        client_id: str,
    ) -> None:
        self._websocket = websocket
        self._audio_queue = audio_queue
        self._signal_queue = signal_queue
        self._client_id = client_id
    async def run(self) -> None:
        """
        Main coroutine.  Runs until the WebSocket closes or an
        unrecoverable error occurs.
        """
        logger.info(f"[{self._client_id}] AudioReceiver started.")
        try:
            async for message in self._websocket:
                if isinstance(message, bytes):
                    await self._audio_queue.put(message)
                    # logger.debug(
                    #     f"[{self._client_id}] AudioReceiver → audio_queue "
                    #     f"({len(message)} bytes)"
                    # )
                else:
                    # Text frame — check for LLM trigger signal
                    text = message.strip()
                    if text.lower() == LLM_TRIGGER_SIGNAL.lower():
                        logger.info(
                            f"[{self._client_id}] AudioReceiver: LLM trigger signal received."
                        )
                        await self._signal_queue.put(text)
                    else:
                        logger.warning(
                            f"[{self._client_id}] AudioReceiver: unrecognised text frame "
                            f"'{text}'. Ignoring."
                        )
        except websockets.exceptions.ConnectionClosed as exc:
            logger.info(
                f"[{self._client_id}] WebSocket closed "
                f"(code={exc.code}, reason='{exc.reason}')."
            )
        except asyncio.CancelledError:
            logger.info(f"[{self._client_id}] AudioReceiver cancelled.")
            raise
        except Exception as exc:
            logger.error(
                f"[{self._client_id}] AudioReceiver unexpected error: {exc}",
                exc_info=True,
            )
        finally:
            # Signal downstream that no more audio or triggers are coming
            await self._audio_queue.put(None)
            await self._signal_queue.put(None)
            logger.info(
                f"[{self._client_id}] AudioReceiver finished — "
                f"EOF sentinels sent to audio_queue and signal_queue."
            )
