"""
llm/llm_pipeline.py

Gemini Prompt-Chaining Pipeline
=================================
Initialises a single Gemini client (via Vertex AI) at module load time
and exposes ``run_pipeline()``, the orchestrator that executes all prompt
steps sequentially, passing each step's JSON output into the next.

Client initialisation
---------------------
Authentication is handled implicitly through Application Default
Credentials — the same ``GOOGLE_APPLICATION_CREDENTIALS`` env-var already
used by the Google STT client.  No extra setup is required.

Adding a new pipeline step
--------------------------
1.  Define PROMPT_STEP_<N>_xxx in ``prompts.py``.
2.  Import it here.
3.  Copy the numbered Step block below, increment N, fill the prompt
    template with whichever variables you need (e.g. previous step's
    JSON), call ``_generate_json()``, and add the result to the
    ``pipeline_result`` dict.
4.  Return the dict — the caller receives all steps' outputs.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from config import GEMINI_MODEL, VERTEX_LOCATION, VERTEX_PROJECT_ID
from llm.prompts import PROMPT_STEP_1, PROMPT_STEP_2
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client — lazy singleton.
# Created on the first actual API call so that:
#   1. Server startup never fails due to network or credential issues.
#   2. Config changes (VERTEX_PROJECT_ID etc.) take effect before first use.
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Return (and lazily create) the shared Gemini client."""
    global _client
    if _client is None:
        logger.info(
            f"Initialising Gemini client — project={VERTEX_PROJECT_ID}, "
            f"location={VERTEX_LOCATION}, model={GEMINI_MODEL}"
        )
        _client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT_ID,
            location=VERTEX_LOCATION,
        )
    return _client


# Shared config that enforces a strict JSON response from the model
_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _generate_json(prompt: str, client_id: str, step_label: str) -> dict:
    """
    Call Gemini with *prompt*, enforce JSON output, and return a parsed dict.

    Parameters
    ----------
    prompt:
        The fully-rendered prompt string (variables already substituted).
    client_id:
        Short session ID for log traceability.
    step_label:
        Human-readable label like "Step 1 / Entity Extraction" for logs.

    Returns
    -------
    dict
        Parsed JSON object from the model response.

    Raises
    ------
    json.JSONDecodeError
        If the model returns something that isn't valid JSON (should be
        rare when response_mime_type="application/json" is set).
    """
    logger.debug(f"[{client_id}] [{step_label}] Sending request to Gemini.")

    response = await _get_client().aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=_JSON_CONFIG,
    )

    raw_text: str = response.text
    logger.debug(f"[{client_id}] [{step_label}] Raw response: {raw_text}")

    parsed: dict = json.loads(raw_text)
    logger.info(f"[{client_id}] [{step_label}] Parsed result: {parsed}")
    return parsed


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

async def run_pipeline(context_text: str, utterance_text: str, client_id: str = "unknown") -> dict:
    """
    Execute the full prompt-chaining pipeline and return all step results.

    Steps run **sequentially**; each step's parsed JSON is available as a
    local variable before the next step's prompt is formatted.

    Parameters
    ----------
    context_text:
        The formatted conversation context from ``SessionMemory.get_context()``.
    client_id:
        Short session ID forwarded to log messages for traceability.

    Returns
    -------
    dict
        ``{"step1": {...}, "step2": {...}, ...}`` — one key per completed step.
    """
    logger.info(
        f"[{client_id}] LLM Pipeline: starting.\n"
        f"  Context ({len(context_text)} chars):\n{context_text}"
    )

    pipeline_result: dict = {}

    # ── Step 1: Entity / Terminology Extraction ────────────────────────────
    step1_prompt = PROMPT_STEP_1.format(context=context_text, utterance=utterance_text)
    step1_result = await _generate_json(
        prompt=step1_prompt,
        client_id=client_id,
        step_label="Step 1 / Entity Extraction",
    )
    pipeline_result["step1"] = step1_result
    step1_entities = step1_result.get("entities", [])   # ← available for Step 2


    # ── Step 2 placeholder ─────────────────────────────────────────────────
    # Uncomment and adapt once PROMPT_STEP_2_xxx is defined in prompts.py.
    #
    # from llm.prompts import PROMPT_STEP_2_SUMMARISE
    step2_prompt = PROMPT_STEP_2.format(entities=step1_entities, 
                                        context=context_text,
                                        utterance=utterance_text)
    step2_result = await _generate_json(
        prompt=step2_prompt,
        client_id=client_id,
        step_label="Step 2 / Priority Estimation"
    )
    pipeline_result["step2"] = step2_result

    # ── Step 3 placeholder ─────────────────────────────────────────────────
    # from llm.prompts import PROMPT_STEP_3_xxx
    # step3_result = await _generate_json(...)
    # pipeline_result["step3"] = step3_result

    logger.info(
        f"[{client_id}] LLM Pipeline: all steps complete. "
        f"Keys returned: {list(pipeline_result.keys())}"
    )
    return pipeline_result
