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

# from langchain_google_vertexai import ChatVertexAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from config import GEMINI_MODEL, VERTEX_LOCATION, VERTEX_PROJECT_ID
from llm.prompts import PROMPT_STEP_1, PROMPT_STEP_2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client — lazy singleton.
# Created on the first actual API call so that:
#   1. Server startup never fails due to network or credential issues.
#   2. Config changes (VERTEX_PROJECT_ID etc.) take effect before first use.
# ---------------------------------------------------------------------------
_step1_chain = None
_step2_chain = None


def _get_chains():
    """Return (and lazily create) the LangChain pipelines."""
    global _step1_chain, _step2_chain
    
    if _step1_chain is None:
        logger.info(
            f"Initialising LangChain Gemini client — project={VERTEX_PROJECT_ID}, "
            f"location={VERTEX_LOCATION}, model={GEMINI_MODEL}"
        )
        
        # 1. 모델 초기화 (JSON 출력 강제 설정 포함)
        llm = ChatGoogleGenerativeAI(
            model_name=GEMINI_MODEL,
            project=VERTEX_PROJECT_ID,
            location=VERTEX_LOCATION,
            temperature=0,
            model_kwargs={"response_mime_type": "application/json"}
        )
        
        # 2. JSON 파서 (모델의 텍스트 응답을 자동으로 dict로 파싱)
        json_parser = JsonOutputParser()

        # 3. 체인 생성 (LCEL 문법: Prompt | LLM | Parser)
        # prompts.py에 정의된 프롬프트 내에 {context}, {utterance}, {entities} 등의 
        # 변수 자리가 비워져 있다고 가정합니다.
        prompt1 = PromptTemplate.from_template(PROMPT_STEP_1)
        _step1_chain = prompt1 | llm | json_parser

        prompt2 = PromptTemplate.from_template(PROMPT_STEP_2)
        _step2_chain = prompt2 | llm | json_parser

    return _step1_chain, _step2_chain


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

async def run_pipeline(context_text: str, utterance_text: str, client_id: str = "unknown") -> dict:
    """
    Execute the full LangChain prompt-chaining pipeline sequentially.
    """
    logger.info(
        f"[{client_id}] LLM Pipeline: starting.\n"
        f"  Context ({len(context_text)} chars):\n{context_text}"
        f"  Utterance ({len(utterance_text)} chars):\n{utterance_text}"
    )

    pipeline_result: dict = {}
    
    # 지연 초기화된 체인 모듈들을 가져옵니다.
    step1_chain, step2_chain = _get_chains()

    # ── Step 1: Entity / Terminology Extraction ────────────────────────────
    logger.debug(f"[{client_id}] [Step 1] Executing LangChain module.")
    
    # ainvoke()를 통해 비동기로 인풋 딕셔너리만 전달합니다.
    step1_result = await step1_chain.ainvoke({
        "context": context_text,
        "utterance": utterance_text
    })
    
    pipeline_result["step1"] = step1_result
    logger.info(f"[{client_id}] [Step 1] Parsed result: {step1_result}")
    
    # 다음 스텝으로 넘길 데이터를 추출합니다.
    step1_entities = step1_result.get("entities", [])


    # ── Step 2: Priority Estimation ─────────────────────────────────────────
    logger.debug(f"[{client_id}] [Step 2] Executing LangChain module.")
    
    # 이전 스텝의 결과를 인풋 변수로 포함하여 전달합니다.
    step2_result = await step2_chain.ainvoke({
        "entities": step1_entities,
        "context": context_text,
        "utterance": utterance_text
    })
    
    pipeline_result["step2"] = step2_result
    logger.info(f"[{client_id}] [Step 2] Parsed result: {step2_result}")

    logger.info(
        f"[{client_id}] LLM Pipeline: all steps complete. "
        f"Keys returned: {list(pipeline_result.keys())}"
    )
    return pipeline_result
