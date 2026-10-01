from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Gap(StrictModel):
    information: str
    question: str
    owner: str
    blocks_testing: bool


class Impact(StrictModel):
    modules: list[str]
    upstream_systems: list[str]
    downstream_systems: list[str]
    regression_areas: list[str]
    evidence: list[str]
    assumptions: list[str]


class Step(StrictModel):
    action: str
    expected_result: str


class TestCase(StrictModel):
    id: str = Field(min_length=1)
    title: str
    type: Literal["manual", "automated"]
    priority: Literal["high", "medium", "low"]
    preconditions: list[str]
    steps: list[Step] = Field(min_length=1)
    acceptance_criteria: list[str]
    data_requirements: list[str]
    automation_framework: str
    automation_outline: str
    blockers: list[str]


class TestPlan(StrictModel):
    scope: list[str]
    out_of_scope: list[str]
    test_levels: list[str]
    environments: list[str]
    entry_criteria: list[str]
    exit_criteria: list[str]
    execution_sequence: list[str]


class TestData(StrictModel):
    customer_data: list[str]
    account_data: list[str]
    api_payloads: list[str]
    integration_data: list[str]
    environment_specific_data: list[str]


class Estimate(StrictModel):
    activity: str
    role: str
    minimum_hours: float = Field(ge=0)
    maximum_hours: float = Field(ge=0)
    assumptions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_range(self):
        if self.maximum_hours < self.minimum_hours:
            raise ValueError("maximum_hours must be at least minimum_hours")
        return self


class Risk(StrictModel):
    description: str
    likelihood: Literal["high", "medium", "low", "unknown"]
    impact: str
    mitigation: str
    evidence: list[str]


class Dependency(StrictModel):
    name: str
    relationship: str
    owner: str
    status: str
    testing_impact: str
    evidence: list[str]


class RequirementAnalysis(StrictModel):
    requirement_summary: str = Field(min_length=1)
    expected_changes: list[str]
    user_journeys: list[str]
    business_impact: list[str]
    missing_information: list[Gap]
    impact_analysis: Impact
    test_cases: list[TestCase] = Field(min_length=1)
    test_plan: TestPlan
    test_data_requirements: TestData
    effort_and_resource_estimates: list[Estimate]
    risk_analysis: list[Risk]
    dependency_analysis: list[Dependency]
    assumptions: list[str]

    @model_validator(mode="after")
    def unique_test_ids(self):
        ids = [test.id for test in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Test case IDs must be unique within a requirement")
        return self
