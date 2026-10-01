from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


A2A_PROTOCOL = "a2a-local-v1"


class A2ARequest(BaseModel):
    """Strongly typed request sent from the Master Orchestrator to an agent."""

    protocol: str = Field(default=A2A_PROTOCOL)
    message_id: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    sender: str
    receiver: str
    message_type: str
    release_id: str
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value != A2A_PROTOCOL:
            raise ValueError(
                f"Invalid A2A protocol. Expected {A2A_PROTOCOL!r}."
            )
        return value

    @field_validator("release_id")
    @classmethod
    def normalize_release_id(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError("release_id is required.")
        return normalized

    @field_validator("sender", "receiver", "message_type")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("A2A text fields cannot be empty.")
        return normalized


class A2AResponse(BaseModel):
    """Strongly typed response sent from an agent back to the Master."""

    protocol: str = Field(default=A2A_PROTOCOL)
    message_id: str
    correlation_id: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    sender: str
    receiver: str
    message_type: str = "A2A_RESPONSE"
    status: str = "COMPLETED"
    release_id: str
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value != A2A_PROTOCOL:
            raise ValueError(
                f"Invalid A2A protocol. Expected {A2A_PROTOCOL!r}."
            )
        return value

    @field_validator("release_id")
    @classmethod
    def normalize_release_id(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise ValueError("release_id is required.")
        return normalized

    @field_validator("sender", "receiver", "message_type", "status")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("A2A text fields cannot be empty.")
        return normalized