"""
llm/prompts.py

Prompt Template Registry
=========================
All LLM prompt strings live here.  Each step is a module-level
constant so it can be imported anywhere without side effects.

Naming convention
-----------------
    PROMPT_STEP_<N>_<SHORT_DESCRIPTION>

    N   — sequential step number in the pipeline
    SHORT_DESCRIPTION — snake_case label for the step's purpose

Adding a new step
-----------------
1.  Define a new constant below (copy the pattern from STEP 1).
2.  Import it in ``llm_pipeline.py`` and add the corresponding
    ``await _client.aio.models.generate_content(...)`` block.
3.  No other files need to change.

Template variables
------------------
Use Python str.format()-style placeholders: {variable_name}.
``llm_pipeline.py`` is responsible for filling them before the API call.
"""

# ===========================================================================
# Step 1 — Entity / Terminology Extraction
# ===========================================================================
# Input variable:
#   {context}  — formatted conversation history from SessionMemory.get_context()
#
# Output schema (enforced by response_mime_type="application/json"):
#   {"entities": ["entity1", "entity2", ...]}
# ===========================================================================
PROMPT_STEP_1_EXTRACT = """\
You are an expert conversation analyst specializing in extracting key information \
from spoken dialogue.

Below is a transcript of a real-time conversation between multiple speakers. \
Analyze the text carefully and extract all of the following:
  - Named entities  (people, organizations, places, product names)
  - Domain-specific terminology or technical jargon
  - Significant nouns or concepts that are central to the discussion

Conversation transcript:
\"\"\"
{context}
\"\"\"

Rules:
- Respond with a single, valid JSON object and nothing else.
- Do NOT include explanations, markdown fences, or extra text.
- Exclude common stopwords, filler words, and pronouns.
- If no meaningful entities are found, return an empty list.

Required JSON format:
{{"entities": ["entity1", "entity2", "entity3"]}}
"""

# ===========================================================================
# Step 2 placeholder — add your next prompt here
# ===========================================================================
# Example: summarise the conversation using the entities from Step 1.
#
# Input variables:
#   {entities}  — JSON list string from Step 1 result
#   {context}   — same conversation context passed to Step 1
#
# Output schema:
#   {"summary": "..."}
#
# PROMPT_STEP_2_SUMMARISE = """\
# You are a concise conversation summariser.
# Given the following key entities: {entities}
# And the conversation:
# \"\"\"
# {context}
# \"\"\"
# Produce a 2-3 sentence summary. Respond only with:
# {{"summary": "your summary here"}}
# """

# ===========================================================================
# Step 3 placeholder — add your next prompt here
# ===========================================================================
# PROMPT_STEP_3_xxx = """\
# ...
# """
