"""
pipeline/audio_receiver.py
Stage 1 — AudioReceiver
========================
Reads raw PCM audio bytes from the WebSocket connection and enqueues
them into ``audio_queue`` for downstream consumption by the STTWorker.
Responsibilities
----------------
- Iterate over incoming WebSocket messages.
- Filter for binary frames only (ignore stray text frames with a warning).
- On connection close or any error, push a ``None`` sentinel to
  ``audio_queue`` so the STTWorker knows the stream has ended.
"""
import asyncio
import logging
import websockets.exceptions
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
    client_id:
        Short identifier used in log messages.
    """
    def __init__(
        self,
        websocket,
        audio_queue: asyncio.Queue,
        client_id: str,
    ) -> None:
        self._websocket = websocket
        self._audio_queue = audio_queue
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
                    # Unexpected text frame — log and ignore
                    logger.warning(
                        f"[{self._client_id}] AudioReceiver received a text frame, "
                        f"expected binary audio.  Ignoring."
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
            # Always signal downstream that no more audio is coming
            await self._audio_queue.put(None)
            logger.info(
                f"[{self._client_id}] AudioReceiver finished — "
                f"EOF sentinel sent to audio_queue."
            )
