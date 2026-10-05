from typing import Literal, Optional
from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    id: str
    text: str


class TestStep(BaseModel):
    step_number: int
    action: str
    expected_result: str


class TestDataEntry(BaseModel):
    key: str
    value: str


class ExistingTestCase(BaseModel):
    test_case_id: str
    title: str

    preconditions: list[str] = Field(default_factory=list)
    test_data: dict = Field(default_factory=dict)
    steps: list[TestStep] = Field(default_factory=list)

    expected_result: Optional[str] = None
    mapped_acceptance_criteria: list[str] = Field(default_factory=list)


class SupplementalContext(BaseModel):
    """Optional non-Jira context (HTML, audio, or a document) supplied by the user.

    `content_base64` / `raw_html` carry the raw, untrusted source payload as
    received from the client. Preprocessing (see `context_extraction.py`)
    resolves these into `extracted_text` / `transcript` and MUST null out
    `content_base64` / `raw_html` before this model is handed to the LLM.
    """

    source_type: Literal["NONE", "HTML", "AUDIO", "FILE"] = "NONE"

    file_name: Optional[str] = None
    mime_type: Optional[str] = None

    content_base64: Optional[str] = None
    raw_html: Optional[str] = None

    extracted_text: Optional[str] = None
    transcript: Optional[str] = None


class GenerationConditions(BaseModel):
    """UI toggles that gate which categories of new test cases may be generated.

    These control ELIGIBILITY for generation, not `test_type` — a scenario
    enabled by `negative_test_cases` may still be the best fit for e.g. a
    STATE_TRANSITION test_type. Default to all-true so requests that omit
    this field entirely (pre-existing Jira-only callers) keep the original,
    unrestricted generation behavior.
    """

    positive_test_cases: bool = True
    negative_test_cases: bool = True
    boundary_conditions: bool = True


class TestCaseGenerationInput(BaseModel):
    epic_key: Optional[str] = None

    story_key: str
    summary: str
    description: str

    priority: Optional[str] = None

    acceptance_criteria: list[AcceptanceCriterion]

    business_rules: list[str] = Field(default_factory=list)

    existing_test_cases: list[ExistingTestCase] = Field(
        default_factory=list
    )

    linked_defects: list[str] = Field(default_factory=list)

    related_issues: list[str] = Field(default_factory=list)

    supplemental_context: SupplementalContext = Field(
        default_factory=SupplementalContext
    )

    generation_conditions: GenerationConditions = Field(
        default_factory=GenerationConditions
    )


# -----------------------------
# Output
# -----------------------------

class CoverageAnalysis(BaseModel):
    acceptance_criterion_id: str

    status: Literal[
        "COVERED",
        "PARTIALLY_COVERED",
        "NOT_COVERED"
    ]

    existing_test_case_ids: list[str] = Field(default_factory=list)

    coverage_gap: Optional[str] = None


class GeneratedTestCase(BaseModel):
    generated_test_id: str

    story_key: str

    title: str

    objective: str

    test_type: Literal[
        "POSITIVE",
        "NEGATIVE",
        "BOUNDARY",
        "STATE_TRANSITION",
        "VALIDATION",
        "REGRESSION",
        "WORKFLOW"
    ]

    test_basis: Literal[
        "ACCEPTANCE_CRITERION",
        "DERIVED",
        "HISTORICAL_DEFECT"
    ]

    priority: Literal[
        "HIGH",
        "MEDIUM",
        "LOW"
    ]

    mapped_acceptance_criteria: list[str]

    coverage_gap: str

    preconditions: list[str]

    test_data: list[TestDataEntry]

    steps: list[TestStep]

    final_expected_result: str

    duplicate_check_notes: str


class TestCaseGenerationResult(BaseModel):

    story_key: str

    requirement_summary: str

    coverage_analysis: list[CoverageAnalysis]

    generated_test_cases: list[GeneratedTestCase]

    clarifications_required: list[str] = Field(default_factory=list)

    generation_summary: str
