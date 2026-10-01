from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Classification(StrEnum):
    MUST_TEST = "MUST_TEST"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"
    EXCLUDE = "EXCLUDE"


class AgentMessage(BaseModel):
    """Structured Agent-to-Agent message used by the local orchestrator."""

    message_id: str
    sender: str
    receiver: str
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentRun(BaseModel):
    """Audit record for one agent or pipeline stage."""

    agent: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None


class PipelineState(BaseModel):
    """Shared state for one complete Risk Tier pipeline execution."""

    release_id: str

    release: dict[str, Any] = Field(default_factory=dict)
    change_impact: dict[str, Any] = Field(default_factory=dict)
    criticality: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    scoring: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)

    messages: list[AgentMessage] = Field(default_factory=list)
    audit_log: list[AgentRun] = Field(default_factory=list)

    report_files: dict[str, str] = Field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        scoring_summary = self.scoring.get("summary", {})
        governance_summary = self.governance.get("summary", {})

        return {
            "release_id": self.release_id,
            "release_type": (
                self.release.get("Release_Type")
                or self.release.get("release_type")
            ),
            "total_tests": scoring_summary.get("total_tests", 0),
            "must_test": scoring_summary.get("MUST_TEST", 0),
            "recommended": scoring_summary.get("RECOMMENDED", 0),
            "optional": scoring_summary.get("OPTIONAL", 0),
            "exclude": scoring_summary.get("EXCLUDE", 0),
            "selected_execution_minutes": scoring_summary.get(
                "selected_execution_minutes",
                0,
            ),
            "full_regression_minutes": scoring_summary.get(
                "full_regression_minutes",
                0,
            ),
            "pending_approvals": governance_summary.get(
                "pending_approvals",
                0,
            ),
            "exclusion_rate": governance_summary.get(
                "exclusion_rate",
                0,
            ),
            "over_exclusion_cap": governance_summary.get(
                "over_cap",
                False,
            ),
            "agent_messages": len(self.messages),
            "agent_runs": len(self.audit_log),
        }