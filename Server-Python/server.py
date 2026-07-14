"""
main.py — ConvAgent Middleware Server  (entry point)

Starts a WebSocket server on WS_HOST:WS_PORT.
Each new connection creates an isolated ClientSession that owns its own
pipeline (AudioReceiver → STTWorker → Dispatcher → ResultSender).

Environment Variables Required
-------------------------------
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

    (Set this before running.  The Google Cloud SDK picks it up
     automatically — no code changes needed.)

Usage
-----
    python main.py

Graceful Shutdown
-----------------
    Send SIGINT (Ctrl+C) or SIGTERM.  The server stops accepting new
    connections and all active sessions are cleaned up before exit.
"""

import asyncio
import logging
import signal
import sys
import os

import websockets

from config import WS_HOST, WS_PORT
from session import ClientSession

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\ProjectWorksapce\ConvAgent\Server-Python\credentials\google-stt-key.json"
# ---------------------------------------------------------------------------
# Logging — change level to logging.INFO for production
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  [%(levelname)-8s]  %(name)-40s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Silence overly verbose third-party loggers in debug mode
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("grpc").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# WebSocket connection handler
# ---------------------------------------------------------------------------

async def connection_handler(websocket) -> None:
    """
    Invoked by the ``websockets`` library for every new incoming
    connection.  Delegates immediately to ClientSession so the handler
    stays thin.
    """
    session = ClientSession(websocket)
    await session.run()


# ---------------------------------------------------------------------------
# Server startup / shutdown
# ---------------------------------------------------------------------------

async def main() -> None:
    logger.info("=" * 60)
    logger.info("  ConvAgent Middleware Server  starting up")
    logger.info("=" * 60)
    logger.info(f"  WebSocket endpoint : ws://{WS_HOST}:{WS_PORT}")
    logger.info("=" * 60)

    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received — stopping server.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, OSError):
            # Windows: add_signal_handler is not fully supported;
            # KeyboardInterrupt from the outer try/except handles Ctrl+C.
            pass

    async with websockets.serve(
        connection_handler,
        WS_HOST,
        WS_PORT,
        # Increase limits for large PCM audio frames
        max_size=10 * 1024 * 1024,  # 10 MB per message
        ping_interval=20,
        ping_timeout=60,
    ):
        logger.info("Server is ready — waiting for Unity client connections.")
        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            pass

    logger.info("Server shut down gracefully.  Goodbye.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
