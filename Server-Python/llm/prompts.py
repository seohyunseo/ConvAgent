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
PROMPT_STEP_1 = """\
You are an entity extraction module for a proactive AR assistant.

Given the previous conversation and the latest utterance,

1. Correct obvious speech recognition errors on 'latest utterance' refering only the 'previous conversation' as context.
2. Extract concepts that are important for understanding the current conversation from only 'latest utterance'.
3. Normalize entities into their canonical names.

'previous conversation' (context):
\"\"\"
{context}
\"\"\"

'latest utterance':
\"\"\"
{utterance}
\"\"\"

Rules:
- Respond with valid JSON objects and nothing else.
- Do NOT include explanations, markdown fences, general nouns, pronouns, common verbs, number (numeric values) or extra text.
- If no meaningful entities are found, return an empty list.

Required JSON format:
{{ "recovered_utterance":"",
   "entities":["", "", ...]
}}
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
PROMPT_STEP_2 = """\
You are a reasoning module for proactive common ground support during face-to-face conversations.
Your task is to estimate which entities should be explained first considering 'priority' and 'shared_knowledge'.

Given,
1. Previous conversation: {context}
2. Latest utterance: {utterance}
3. Extracted entities: {entities}
4. Entities memory: TBD

Evaluate 'priority' of each entity using the following criteria.

1. Context Relevance
How essential is the entity for understanding the current conversation?

2. Dependency
Does understanding other entities depend on understanding this entity?

3. Future Impact
Is this entity likely to be referenced again later in the conversation?

4. Recoverability
Can the conversation still be understood without knowing this entity?

5. Explanation Benefit
Would explaining this entity improve understanding of multiple parts of the conversation?

Evaluate 'shared_knowledge' of each entity using the following criteria.

1. Conversational Familiarity
How familiar with this entity is the user in this conversation?

2. Domain Difficulty
How difficult is this entity to understand for the general user with only a few domain knowledge?

3. Explanation History
Has this entity been explained before?

Return only JSON.

{{
    "priority_entities":
        {{"entity":"",
          "priority":0.0,
          "shared_knowledge":0.0}}
}}

Priority and Shared Knowledge should be normalized between 0 and 1.
"""
