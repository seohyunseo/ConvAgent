"""
pipeline/result_sender.py

Stage 4 — ResultSender
=======================
Receives a transcript payload dict from the Dispatcher and sends it
back to the Unity client as a UTF-8 JSON string over WebSocket.

JSON Payload sent to Unity
--------------------------
    {
        "transcript": "안녕하세요",   // recognised text
        "isFinal":    true,           // stable final result?
        "speakerTag": 2               // 0 = unknown / interim
    }
"""

import json
import logging

import websockets.exceptions

logger = logging.getLogger(__name__)


class ResultSender:
    """
    Parameters
    ----------
    websocket:
        The active WebSocket connection for this client.
    client_id:
        Short identifier used in log messages.
    """

    def __init__(self, websocket, client_id: str) -> None:
        self._websocket = websocket
        self._client_id = client_id

    async def send(self, payload: dict) -> None:
        """
        Handler registered with the Dispatcher.

        Serialises *payload* to a JSON string and sends it to the
        Unity client.  Connection-closed errors are logged as warnings
        (not exceptions) since they are expected during normal shutdown.
        """
        try:
            message = json.dumps(payload, ensure_ascii=False)
            await self._websocket.send(message)
            # logger.debug(f"[{self._client_id}] ResultSender → client: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning(
                f"[{self._client_id}] ResultSender: WebSocket already closed, "
                f"dropping payload."
            )
        except Exception as exc:
            logger.error(
                f"[{self._client_id}] ResultSender error: {exc}", exc_info=True
            )
