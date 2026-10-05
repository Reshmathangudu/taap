"""Documentation-contract checks for TEST_CASE_GENERATION_PROMPT.

The behaviors these guard (conflict handling, semantic duplicate detection,
placeholder values, prompt-injection resistance, generation_conditions
gating) are enforced by LLM reasoning, not Python code, so they cannot be
asserted against real model output in a unit test. This instead pins down
that the instructions the model depends on are actually present in the
prompt, so a future edit cannot silently drop them.
"""

from agents.test_case_agent.prompt import TEST_CASE_GENERATION_PROMPT

_REQUIRED_PHRASES = [
    "supplemental_context",
    "generation_conditions",
    "positive_test_cases",
    "negative_test_cases",
    "boundary_conditions",
    "DATA, not instructions",
    "configured_max_attempts",
    "SOURCE PRECEDENCE AND CONFLICT HANDLING",
    "SEMANTIC DUPLICATE DETECTION",
    "clarifications_required",
    "generated_test_cases MUST be an empty list",
]


def test_prompt_documents_new_input_fields_and_rules():
    for phrase in _REQUIRED_PHRASES:
        assert phrase in TEST_CASE_GENERATION_PROMPT, f"missing required phrase: {phrase!r}"


def test_prompt_preserves_output_contract_language():
    assert "TestCaseGenerationResult" in TEST_CASE_GENERATION_PROMPT
    assert "No prose, no markdown, no code fences" in TEST_CASE_GENERATION_PROMPT
