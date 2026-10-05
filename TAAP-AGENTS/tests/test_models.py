from agents.test_case_agent.models import (
    GenerationConditions,
    SupplementalContext,
    TestCaseGenerationInput,
)


def test_legacy_jira_only_payload_still_validates():
    """A pre-existing caller that sends none of the new fields must keep working."""

    payload = {
        "story_key": "PROJ-1",
        "summary": "Login",
        "description": "User logs in with username/password.",
        "acceptance_criteria": [{"id": "AC-1", "text": "Valid credentials succeed."}],
    }

    parsed = TestCaseGenerationInput.model_validate(payload)

    assert parsed.supplemental_context.source_type == "NONE"
    assert parsed.generation_conditions.positive_test_cases is True
    assert parsed.generation_conditions.negative_test_cases is True
    assert parsed.generation_conditions.boundary_conditions is True


def test_generation_conditions_defaults_all_true():
    assert GenerationConditions().model_dump() == {
        "positive_test_cases": True,
        "negative_test_cases": True,
        "boundary_conditions": True,
    }


def test_supplemental_context_defaults_to_none_source():
    context = SupplementalContext()
    assert context.source_type == "NONE"
    assert context.file_name is None
    assert context.mime_type is None
    assert context.content_base64 is None
    assert context.raw_html is None
    assert context.extracted_text is None
    assert context.transcript is None


def test_generation_conditions_can_be_explicitly_disabled():
    payload = {
        "story_key": "PROJ-1",
        "summary": "Login",
        "description": "User logs in.",
        "acceptance_criteria": [{"id": "AC-1", "text": "Valid credentials succeed."}],
        "generation_conditions": {
            "positive_test_cases": False,
            "negative_test_cases": True,
            "boundary_conditions": False,
        },
    }

    parsed = TestCaseGenerationInput.model_validate(payload)

    assert parsed.generation_conditions.positive_test_cases is False
    assert parsed.generation_conditions.negative_test_cases is True
    assert parsed.generation_conditions.boundary_conditions is False
