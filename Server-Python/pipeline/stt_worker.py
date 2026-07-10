"""
pipeline/stt_worker.py

Stage 2 — STTWorker
====================
Consumes audio bytes from ``audio_queue``, streams them to the Google
Cloud Speech-to-Text v1 API (StreamingRecognize), and pushes parsed
transcript dictionaries into ``transcript_queue``.

Threading Bridge
----------------
The ``google-cloud-speech`` client uses a **synchronous** gRPC iterator.
Running this directly in the asyncio event loop would block it entirely.
Instead, STTWorker uses a two-layer bridge:

    asyncio.Queue (audio_queue)
        │  [_audio_forwarder coroutine — runs in event loop]
        ▼
    threading.Queue (thread_audio_q)
        │  [_blocking_stt_worker function — runs in ThreadPoolExecutor]
        ▼
    gRPC streaming_recognize call + response parsing
        │  [asyncio.run_coroutine_threadsafe — thread-safe push back]
        ▼
    asyncio.Queue (transcript_queue)

Cancellation
------------
When the asyncio Task is cancelled (e.g. client disconnects abruptly),
a ``threading.Event`` (``_stop_event``) is set and a sentinel is pushed
to the ``threading.Queue`` so the gRPC request generator unblocks within
the next polling interval (<=``_THREAD_QUEUE_TIMEOUT`` seconds).

Output Payload Schema
---------------------
    {
        "transcript": str,    # recognised text
        "isFinal":    bool,   # True when this is a stable final result
        "speakerTag": int,    # 0 = unknown / interim; >=1 = diarized speaker
    }
"""

import asyncio
import logging
import queue as thread_queue_module
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from google.cloud import speech

from config import (
    AUDIO_LANGUAGE,
    AUDIO_SAMPLE_RATE,
    DIARIZATION_MAX_SPEAKERS,
    DIARIZATION_MIN_SPEAKERS,
    THREAD_QUEUE_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Shared thread pool — reused across all sessions
_THREAD_POOL = ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="stt-worker",
)


class STTWorker:
    """
    Parameters
    ----------
    audio_queue:
        Source of ``bytes`` chunks.  ``None`` = end of stream.
    transcript_queue:
        Sink for parsed transcript dicts.  ``None`` sentinel is sent
        when this worker finishes.
    client_id:
        Short identifier used in log messages.
    """

    def __init__(
        self,
        audio_queue: asyncio.Queue,
        transcript_queue: asyncio.Queue,
        client_id: str,
    ) -> None:
        self._audio_queue = audio_queue
        self._transcript_queue = transcript_queue
        self._client_id = client_id
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public — asyncio entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """
        Starts the audio forwarder coroutine and the blocking gRPC
        worker (in a thread), then waits for both to finish.
        """
        logger.info(f"[{self._client_id}] STTWorker started.")
        loop = asyncio.get_running_loop()
        thread_audio_q: thread_queue_module.Queue = thread_queue_module.Queue()

        forwarder_task = asyncio.create_task(
            self._audio_forwarder(thread_audio_q),
            name=f"audio-forwarder-{self._client_id}",
        )

        try:
            # Run blocking gRPC call in thread pool; await its completion
            await loop.run_in_executor(
                _THREAD_POOL,
                self._blocking_stt_worker,
                thread_audio_q,
                loop,
            )
        except asyncio.CancelledError:
            logger.info(f"[{self._client_id}] STTWorker task cancelled — stopping thread.")
            self._stop_event.set()
            thread_audio_q.put(None)  # unblock thread_audio_q.get() in the thread
            raise
        except Exception as exc:
            logger.error(
                f"[{self._client_id}] STTWorker run error: {exc}", exc_info=True
            )
        finally:
            # Ensure the forwarder coroutine is stopped
            if not forwarder_task.done():
                forwarder_task.cancel()
                try:
                    await forwarder_task
                except asyncio.CancelledError:
                    pass

            # Signal the Dispatcher that no more transcripts will arrive
            await self._transcript_queue.put(None)
            logger.info(
                f"[{self._client_id}] STTWorker finished — "
                f"EOF sentinel sent to transcript_queue."
            )

    # ------------------------------------------------------------------
    # Private — asyncio side
    # ------------------------------------------------------------------

    async def _audio_forwarder(
        self, thread_audio_q: thread_queue_module.Queue
    ) -> None:
        """
        Drains ``audio_queue`` (asyncio) and relays chunks to
        ``thread_audio_q`` (threading) so the blocking thread can
        consume them.
        """
        try:
            while True:
                chunk: Optional[bytes] = await self._audio_queue.get()
                thread_audio_q.put(chunk)  # None sentinel is also forwarded
                if chunk is None:
                    break
        except asyncio.CancelledError:
            # Make sure the thread isn't stuck waiting for more audio
            thread_audio_q.put(None)
            raise

    # ------------------------------------------------------------------
    # Private — thread side
    # ------------------------------------------------------------------

    def _blocking_stt_worker(
        self,
        thread_audio_q: thread_queue_module.Queue,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """
        Executed entirely inside a ThreadPoolExecutor worker thread.

        1. Builds the gRPC request generator backed by ``thread_audio_q``.
        2. Calls ``client.streaming_recognize()`` (blocking iterator).
        3. Parses each response and pushes the payload to
           ``transcript_queue`` via ``asyncio.run_coroutine_threadsafe``.
        """
        client = speech.SpeechClient()

        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=AUDIO_SAMPLE_RATE,
            language_code=AUDIO_LANGUAGE,
            diarization_config=speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=DIARIZATION_MIN_SPEAKERS,
                max_speaker_count=DIARIZATION_MAX_SPEAKERS,
            ),
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True,
        )

        def request_generator():
            # Subsequent messages: audio chunks from the threading queue
            while not self._stop_event.is_set():
                try:
                    chunk = thread_audio_q.get(timeout=THREAD_QUEUE_TIMEOUT)
                except thread_queue_module.Empty:
                    # Timeout — loop back and check stop_event again
                    continue
                if chunk is None:
                    logger.debug(
                        f"[{self._client_id}] STT request generator: EOF sentinel received."
                    )
                    break
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

        try:
            logger.info(
                f"[{self._client_id}] Opening Google STT StreamingRecognize session."
            )
            responses = client.streaming_recognize(requests=request_generator(), config=streaming_config)

            for response in responses:
                for result in response.results:
                    if not result.alternatives:
                        continue

                    alternative = result.alternatives[0]
                    is_final: bool = result.is_final
                    transcript: str = alternative.transcript
                    speaker_tag: int = self._extract_speaker_tag(
                        alternative, is_final
                    )

                    payload = {
                        "transcript": transcript,
                        "isFinal": is_final,
                        "speakerTag": speaker_tag,
                    }

                    if(is_final):
                        logger.info(
                            f"[{self._client_id}] STT result "
                            f"(final={is_final}, speaker={speaker_tag}): "
                            f"'{transcript}'"
                        )

                    # Thread-safe push into asyncio transcript_queue
                    future = asyncio.run_coroutine_threadsafe(
                        self._transcript_queue.put(payload), loop
                    )
                    # Block this thread briefly to apply back-pressure if
                    # the dispatcher is falling behind
                    future.result(timeout=5.0)

        except Exception as exc:
            logger.error(
                f"[{self._client_id}] Blocking STT worker error: {exc}",
                exc_info=True,
            )
        finally:
            logger.info(
                f"[{self._client_id}] Google STT StreamingRecognize session closed."
            )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_speaker_tag(alternative, is_final: bool) -> int:
        """
        Extract a speaker tag from word-level diarization info.

        Google Speech-to-Text only populates ``speaker_tag`` on *final*
        results.  For interim results we return ``0`` (unknown).

        For final results the tag of the *last* word is returned, which
        represents the speaker who was talking at the end of the utterance.
        """
        if not is_final:
            return 0
        if alternative.words:
            return alternative.words[-1].speaker_tag
        return 0
